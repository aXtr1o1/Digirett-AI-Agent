import os
from lxml import etree as ET
from ingestion.src.config import CLEAN_TEXT_DIR
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('xml_processing.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def extract_all_metadata(root):
    """
    Dynamically extracts ALL metadata from XML header.
    Finds all dt/dd pairs and preserves their exact labels.
    """
    metadata = []  # Use list to preserve order
    
    # Find document header
    header = root.find(".//header[@class='documentHeader']")
    if header is None:
        header = root.find(".//header")
    if header is None:
        header = root
    
    # Find all dt elements (field labels)
    dt_elements = header.findall(".//dt")
    
    for dt in dt_elements:
        # Get label text (what's displayed to user)
        label_text = "".join(dt.itertext()).strip()
        if not label_text:
            continue
        
        # Find corresponding dd element (the value)
        dd = None
        next_sibling = dt.getnext()
        if next_sibling is not None and next_sibling.tag == 'dd':
            dd = next_sibling
        
        if dd is not None:
            # Check for list structure (ul/li)
            ul = dd.find('.//ul')
            if ul is not None:
                items = []
                for li in ul.findall('.//li'):
                    # Get all text including nested elements
                    text = "".join(li.itertext()).strip()
                    if text:
                        items.append(text)
                if items:
                    metadata.append((label_text, items))
            else:
                # Regular text content - get all text including nested elements
                text = "".join(dd.itertext()).strip()
                if text:
                    metadata.append((label_text, text))
    
    return metadata


def find_year_in_text(text):
    """
    Searches for any 4-digit year (1600-2099) in text.
    """
    if not text:
        return None
    
    words = text.replace('-', ' ').replace('/', ' ').replace('.', ' ').replace(':', ' ').split()
    for word in words:
        # Remove any trailing/leading punctuation
        clean_word = word.strip('.,;:!?()[]{}"\'-')
        if clean_word.isdigit() and len(clean_word) == 4:
            year_int = int(clean_word)
            if 1600 <= year_int <= 2099:
                return clean_word
    return None


def extract_year(metadata):
    """
    Extracts year from metadata list.
    """
    # Search through all metadata values
    for label, value in metadata:
        if isinstance(value, list):
            for item in value:
                year = find_year_in_text(item)
                if year:
                    return year
        else:
            year = find_year_in_text(value)
            if year:
                return year
    return None


def format_metadata_header(metadata, year):
    """
    Formats metadata exactly as shown in samples.
    Field Name
        - Value
    """
    lines = []
    
    # Add all metadata fields
    for label, value in metadata:
        lines.append(label)
        
        if isinstance(value, list):
            # Multi-value field
            for item in value:
                lines.append(f"    - {item}")
        else:
            # Single value
            lines.append(f"    - {value}")
    
    # Add year if found
    if year:
        lines.append(f"YEAR: {year}")
    
    # Add separator
    lines.append("-" * 40)
    
    return "\n".join(lines)


def extract_document_body(main_body):
    """
    Extracts document content with full structure preservation.
    Handles all heading levels, paragraphs, sections, and lists.
    """
    lines = []
    seen_text = set()  # Avoid duplicates
    
    # Get main title (h1)
    h1 = main_body.find(".//h1")
    if h1 is not None:
        title = "".join(h1.itertext()).strip()
        if title and title not in seen_text:
            lines.append(title)
            seen_text.add(title)
    
    # Process all elements in order
    for element in main_body.iter():
        tag = element.tag
        classes = element.get('class', '')
        
        # Skip if this element is inside another we'll process
        if element.getparent() is not None:
            parent_tag = element.getparent().tag
            parent_class = element.getparent().get('class', '')
            # Skip text inside article/p elements that will be processed as whole
            if parent_tag in ['article', 'p'] and tag in ['span', 'strong', 'em']:
                continue
        
        # All heading levels (h1-h6)
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            header_text = "".join(element.itertext()).strip()
            if header_text and header_text not in seen_text:
                # h1 already added above, skip duplicate
                if tag == 'h1' and header_text in seen_text:
                    continue
                lines.append(f"\n{header_text}")
                seen_text.add(header_text)
        
        # Paragraphs with legal/default classes
        elif tag == 'article' and any(cls in classes for cls in ['legalP', 'defaultP', 'numberedLegalP', 'futureLegalArticle']):
            # Get all text from this article
            para_text = "".join(element.itertext()).strip()
            
            if para_text and para_text not in seen_text:
                # Check for numbering
                numerator = element.get('data-numerator', '').strip()
                
                if numerator:
                    lines.append(f"\n({numerator}) {para_text}")
                else:
                    lines.append(f"\n{para_text}")
                
                seen_text.add(para_text)
        
        # Regular paragraphs
        elif tag == 'p' and any(cls in classes for cls in ['legalP', 'defaultP']):
            para_text = "".join(element.itertext()).strip()
            if para_text and para_text not in seen_text:
                lines.append(f"\n{para_text}")
                seen_text.add(para_text)
        
        # List items with identifiers
        elif tag == 'li':
            # Skip if inside table of contents
            parent = element.getparent()
            while parent is not None:
                if parent.get('class') == 'table-of-contents':
                    break
                parent = parent.getparent()
            else:
                # Not in TOC, process it
                identifier = element.get('data-li-identifier', '').strip()
                if not identifier:
                    identifier = element.get('data-name', '').strip()
                
                item_text = "".join(element.itertext()).strip()
                
                # Remove identifier from text if already at start
                if identifier and item_text.startswith(identifier):
                    item_text = item_text[len(identifier):].strip()
                
                if item_text and item_text not in seen_text:
                    if identifier:
                        lines.append(f"  {identifier} {item_text}")
                    else:
                        lines.append(f"  {item_text}")
                    seen_text.add(item_text)
    
    return lines


def xml_to_structured_text(xml_path, file_name):
    """
    Converts ANY Norwegian legal XML to structured text format.
    Fully dynamic - adapts to any structure automatically.
    Handles 10,000+ files with different formats.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logging.error(f"XML Parse Error [{file_name}]: {e}")
        return ""
    except FileNotFoundError:
        logging.error(f"File Not Found [{file_name}]: {xml_path}")
        return ""
    except Exception as e:
        logging.error(f"Error parsing [{file_name}]: {e}")
        return ""
    
    try:
        # Extract all metadata dynamically
        metadata = extract_all_metadata(root)
        
        # Find year from metadata
        year = extract_year(metadata)
        
        # Format metadata header
        header = format_metadata_header(metadata, year)
        
        # Extract document body
        main_body = root.find(".//main")
        if main_body is None:
            main_body = root.find(".//body")
        if main_body is None:
            main_body = root
        
        content_lines = extract_document_body(main_body)
        
        # Combine header + content
        full_text = header + "\n" + "\n".join(content_lines).strip()
        
        return full_text
        
    except Exception as e:
        logging.error(f"Content extraction error [{file_name}]: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return ""


def process_single_file(xml_path):
    """
    Processes one XML file atomically.
    Returns processing status.
    """
    if not isinstance(xml_path, (str, os.PathLike)):
        raise TypeError(f"Expected xml_path to be str or Path, got {type(xml_path)}")

    base_name = os.path.basename(xml_path)
    txt_name = base_name.replace(".xml", ".txt")

    text_content = xml_to_structured_text(xml_path, txt_name)

    if not text_content:
        return {'status': 'failed', 'file': txt_name}

    output_path = os.path.join(CLEAN_TEXT_DIR, txt_name)
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text_content)
    except Exception as e:
        logging.error(f"File write error [{txt_name}]: {e}")
        return {'status': 'failed', 'file': txt_name}

    has_year = "YEAR:" in text_content

    return {
        'status': 'success',
        'file': txt_name,
        'has_year': has_year
    }


def process_xml_to_text(xml_files, max_workers=4):
    """
    Batch processes XML files to structured text format.
    Optimized for 10,000+ files with different structures.
    
    Args:
        xml_files: List of XML file paths
        max_workers: Number of parallel workers (default: 4)
    
    Returns:
        List of document dictionaries with 'file_name' and 'text' keys
    """
    os.makedirs(CLEAN_TEXT_DIR, exist_ok=True)
    
    documents = []
    stats = {
        'total': len(xml_files),
        'success': 0,
        'failed': 0,
        'no_year': 0,
        'failed_files': []
    }
    
    logging.info(f"Starting batch processing: {stats['total']} files")
    
    # Parallel processing with progress bar
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single_file, path): path for path in xml_files}
        
        with tqdm(total=stats['total'], desc="Processing XML files", unit="file") as pbar:
            for future in as_completed(futures):
                result = future.result()
                
                if result['status'] == 'success':
                    stats['success'] += 1
                    
                    # Read the saved file content
                    txt_path = os.path.join(CLEAN_TEXT_DIR, result['file'])
                    try:
                        with open(txt_path, 'r', encoding='utf-8') as f:
                            text_content = f.read()
                        
                        documents.append({
                            'file_name': result['file'],
                            'text': text_content
                        })
                    except Exception as e:
                        logging.error(f"Error reading saved file [{result['file']}]: {e}")
                    
                    if not result['has_year']:
                        stats['no_year'] += 1
                else:
                    stats['failed'] += 1
                    stats['failed_files'].append(result['file'])
                
                pbar.update(1)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"BATCH PROCESSING COMPLETED")
    print(f"{'='*60}")
    print(f"  Total files:         {stats['total']}")
    print(f"  ✓ Successful:        {stats['success']} ({stats['success']/stats['total']*100:.1f}%)")
    print(f"  ✗ Failed:            {stats['failed']} ({stats['failed']/stats['total']*100:.1f}%)")
    print(f"  ⚠ Without year:      {stats['no_year']} ({stats['no_year']/max(stats['success'],1)*100:.1f}% of successful)")
    print(f"{'='*60}")
    
    # Show failed files
    if stats['failed_files']:
        print(f"\n⚠ Failed files ({len(stats['failed_files'])}):")
        for i, fname in enumerate(stats['failed_files'][:10], 1):
            print(f"  {i}. {fname}")
        if len(stats['failed_files']) > 10:
            print(f"  ... and {len(stats['failed_files']) - 10} more")
        print(f"\nCheck 'xml_processing.log' for details\n")
    
    logging.info(f"Batch processing completed: {stats['success']}/{stats['total']} successful")
    logging.info(f"Returning {len(documents)} documents for further processing")
    
    return documents