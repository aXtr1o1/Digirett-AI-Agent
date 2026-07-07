import { useState, useEffect } from 'react';

// Detect touch-capable devices. Uses multiple heuristics for robustness.
export function detectTouchDevice() {
  if (typeof window === 'undefined') return false;
  try {
    const hasTouchEvents = 'ontouchstart' in window;
    const hasMaxTouchPoints = typeof navigator !== 'undefined' && navigator.maxTouchPoints > 0;
    const coarsePointer = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
    return !!hasTouchEvents || !!hasMaxTouchPoints || !!coarsePointer;
  } catch (e) {
    return false;
  }
}

export function isDesktopLike(screen) {
  return screen === 'desktop' || screen === 'tablet';
}

// Tablet/iPad hybrid mapping: desktop-layout for 641-1024 and tablet sizing, not mobile auto size
export function getHybridResponsiveState(width) {
  if (width <= 640) {
    return { screen: 'mobile', isDesktopLayout: false, sizingScreen: 'mobile' };
  }

  if (width <= 1024) {
    return { screen: 'tablet', isDesktopLayout: true, sizingScreen: 'tablet' };
  }

  return { screen: 'desktop', isDesktopLayout: true, sizingScreen: 'desktop' };
}

export function useResponsive() {
  // Calculate initial state based on actual window width
  const getInitialState = () => {
    if (typeof window === 'undefined') {
      // SSR: default to desktop for initial render
      return {
        isMobile: false,
        isTablet: false,
        isDesktop: true,
        isTouch: false,
        isDesktopLayout: true,
        screen: 'desktop',
        sizingScreen: 'desktop',
        width: 1024,
        height: 768,
      };
    }

    const width = window.innerWidth;
    const height = window.innerHeight;
    const hybrid = getHybridResponsiveState(width);

    return {
      isMobile: hybrid.screen === 'mobile' && !hybrid.isDesktopLayout,
      isTablet: hybrid.screen === 'tablet',
      isDesktop: hybrid.screen === 'desktop',
      isTouch: detectTouchDevice(),
      isDesktopLayout: hybrid.isDesktopLayout,
      screen: hybrid.screen,
      sizingScreen: hybrid.sizingScreen,
      width,
      height,
    };
  };

  const [responsive, setResponsive] = useState(getInitialState());

  useEffect(() => {
    let debounceTimer;

    const updateResponsive = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const hybrid = getHybridResponsiveState(width);

      setResponsive({
        isMobile: hybrid.screen === 'mobile' && !hybrid.isDesktopLayout,
        isTablet: hybrid.screen === 'tablet',
        isDesktop: hybrid.screen === 'desktop',
        isTouch: detectTouchDevice(),
        isDesktopLayout: hybrid.isDesktopLayout,
        screen: hybrid.screen,
        sizingScreen: hybrid.sizingScreen,
        width,
        height,
      });
    };

    const handleResize = () => {
      // Debounce: wait 20ms after resize stops before updating
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(updateResponsive, 20);
    };

    // Set initial size immediately
    updateResponsive();

    // Add resize listener
    window.addEventListener('resize', handleResize);
   
    // Add orientationchange listener for mobile devices (Instant response)
    window.addEventListener('orientationchange', updateResponsive);

    // Cleanup
    return () => {
      clearTimeout(debounceTimer);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', updateResponsive);
    };
  }, []);

  return responsive;
}

/**
 * Alternative: Media Query matcher hook
 * Use this if you want CSS-based media queries with React
 */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(query);
   
    // Set initial state
    if (media.matches !== matches) {
      setMatches(media.matches);
    }

    // Create listener
    const listener = (e) => {
      setMatches(e.matches);
    };

    // Add listener
    media.addEventListener('change', listener);

    // Cleanup
    return () => media.removeEventListener('change', listener);
  }, [matches, query]);

  return matches;
}

export function getResponsiveFontSizes(screen) {
  switch (screen) {
    case 'mobile':
      return {
        heading: '20px',
        subheading: '16px',
        body: '13px',
        small: '12px',
        caption: '11px',
      };
    case 'tablet':
      return {
        heading: '24px',
        subheading: '18px',
        body: '14px',
        small: '13px',
        caption: '12px',
      };
    case 'desktop':
      return {
        heading: '28px',
        subheading: '20px',
        body: '16px',
        small: '14px',
        caption: '13px',
      };
    default:
      return {
        heading: '28px',
        subheading: '20px',
        body: '16px',
        small: '14px',
        caption: '13px',
      };
  }
}

export function getResponsiveSpacing(screen) {
  switch (screen) {
    case 'mobile':
      return {
        xs: '4px',
        sm: '8px',
        md: '12px',
        lg: '16px',
        xl: '20px',
      };
    case 'tablet':
      return {
        xs: '6px',
        sm: '12px',
        md: '16px',
        lg: '20px',
        xl: '24px',
      };
    case 'desktop':
      return {
        xs: '8px',
        sm: '16px',
        md: '20px',
        lg: '24px',
        xl: '32px',
      };
    default:
      return {
        xs: '8px',
        sm: '16px',
        md: '20px',
        lg: '24px',
        xl: '32px',
      };
  }
}

export function getResponsiveTileGrid(screen) {
  switch (screen) {
    case 'mobile':
      return {
        columns: 'repeat(auto-fit, minmax(100px, 1fr))',
        gap: '10px',
        minWidth: '100px',
      };
    case 'tablet':
      return {
        columns: 'repeat(auto-fit, minmax(120px, 1fr))',
        gap: '16px',
        minWidth: '120px',
      };
    case 'desktop':
      return {
        columns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: '20px',
        minWidth: '140px',
      };
    default:
      return {
        columns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: '20px',
        minWidth: '140px',
      };
  }
}

export function getResponsiveMessageBubble(screen) {
  switch (screen) {
    case 'mobile':
      return {
        fontSize: '13px',
        padding: '8px 12px',
        borderRadius: '12px',
        maxWidth: '90%',
      };
    case 'tablet':
      return {
        fontSize: '14px',
        padding: '10px 14px',
        borderRadius: '14px',
        maxWidth: '85%',
      };
    case 'desktop':
      return {
        fontSize: '15px',
        padding: '12px 16px',
        borderRadius: '16px',
        maxWidth: '75%',
      };
    default:
      return {
        fontSize: '15px',
        padding: '12px 16px',
        borderRadius: '16px',
        maxWidth: '75%',
      };
  }
}

export function getResponsiveChart(screen) {
  switch (screen) {
    case 'mobile':
      return {
        maxWidth: '100%',
        height: '350px',
        overflowX: 'auto',
        titleSize: '14px',
        showLegend: false,
      };
    case 'tablet':
      return {
        maxWidth: '500px',
        height: '420px',
        overflowX: 'hidden',
        titleSize: '16px',
        showLegend: true,
      };
    case 'desktop':
      return {
        maxWidth: '600px',
        height: '520px',
        overflowX: 'hidden',
        titleSize: '18px',
        showLegend: true,
      };
    default:
      return {
        maxWidth: '600px',
        height: '520px',
        overflowX: 'hidden',
        titleSize: '18px',
        showLegend: true,
      };
  }
}

export function getResponsiveContainer(screen) {
  switch (screen) {
    case 'mobile':
      return {
        maxWidth: '100%',
        padding: '12px',
        borderRadius: '8px',
      };
    case 'tablet':
      return {
        maxWidth: 'calc(100vw - 180px)',
        padding: '16px',
        borderRadius: '12px',
      };
    case 'desktop':
      return {
        maxWidth: 'calc(100vw - 260px)',
        padding: '20px',
        borderRadius: '16px',
      };
    default:
      return {
        maxWidth: 'calc(100vw - 260px)',
        padding: '20px',
        borderRadius: '16px',
      };
  }
}

export function getResponsiveTable(screen) {
  switch (screen) {
    case 'mobile':
      return {
        fontSize: '12px',
        padding: '6px 10px',
        compactMode: true,
        columnsVisible: 2,
      };
    case 'tablet':
      return {
        fontSize: '13px',
        padding: '8px 12px',
        compactMode: false,
        columnsVisible: 3,
      };
    case 'desktop':
      return {
        fontSize: '14px',
        padding: '10px 14px',
        compactMode: false,
        columnsVisible: 5,
      };
    default:
      return {
        fontSize: '14px',
        padding: '10px 14px',
        compactMode: false,
        columnsVisible: 5,
      };
  }
}

export function getResponsiveSidebar(screen) {
  switch (screen) {
    case 'mobile':
      return {
        width: '240px',
        isVisible: false,
        isOverlay: true,
        position: 'fixed',
      };
    case 'tablet':
      return {
        width: '260px',
        isVisible: true,
        isOverlay: false,
        position: 'relative',
      };
    case 'desktop':
      return {
        width: '260px',
        isVisible: true,
        isOverlay: false,
        position: 'relative',
      };
    default:
      return {
        width: '260px',
        isVisible: true,
        isOverlay: false,
        position: 'relative',
      };
  }
}

export function getResponsiveTileDataConfig(screen) {
  switch (screen) {
    case 'mobile':
      return {
        showFields: ['label', 'value', 'status'],
        maxFields: 2,
        showLabelOnly: false,
        compact: true,
        truncateLength: 15,
      };
    case 'tablet':
      return {
        showFields: ['label', 'value', 'status', 'unit'],
        maxFields: 3,
        showLabelOnly: false,
        compact: false,
        truncateLength: 25,
      };
    case 'desktop':
      return {
        showFields: ['label', 'value', 'status', 'unit', 'change', 'date'],
        maxFields: 6,
        showLabelOnly: false,
        compact: false,
        truncateLength: 50,
      };
    default:
      return {
        showFields: ['label', 'value', 'status', 'unit', 'change', 'date'],
        maxFields: 6,
        showLabelOnly: false,
        compact: false,
        truncateLength: 50,
      };
  }
}

export function getResponsiveTableColumns(screen) {
  switch (screen) {
    case 'mobile':
      return {
        visibleColumns: ['name', 'value', 'status'],
        maxColumns: 3,
        hideSecondaryData: true,
        rowHeight: '36px',
        cellPadding: '6px 8px',
        fontSize: '12px',
        abbreviateHeaders: true,
      };
    case 'tablet':
      return {
        visibleColumns: ['name', 'status', 'value', 'unit', 'date'],
        maxColumns: 5,
        hideSecondaryData: false,
        rowHeight: '40px',
        cellPadding: '8px 12px',
        fontSize: '13px',
        abbreviateHeaders: false,
      };
    case 'desktop':
      return {
        visibleColumns: ['name', 'status', 'value', 'unit', 'change', 'date', 'description'],
        maxColumns: 7,
        hideSecondaryData: false,
        rowHeight: '44px',
        cellPadding: '10px 14px',
        fontSize: '14px',
        abbreviateHeaders: false,
      };
    default:
      return {
        visibleColumns: ['name', 'status', 'value', 'unit', 'change', 'date', 'description'],
        maxColumns: 7,
        hideSecondaryData: false,
        rowHeight: '44px',
        cellPadding: '10px 14px',
        fontSize: '14px',
        abbreviateHeaders: false,
      };
  }
}

export function getResponsiveChartDisplay(screen) {
  switch (screen) {
    case 'mobile':
      return {
        alignment: 'flex-start',
        marginX: '0px',
        marginY: '0px',
        legendPosition: 'hidden',
        showGrid: false,
        showTooltip: true,
        animationEnabled: false,
        responsiveWidth: '100%',
        containerJustify: 'flex-start',
      };
    case 'tablet':
      return {
        alignment: 'center',
        marginX: 'auto',
        marginY: '12px',
        legendPosition: 'bottom',
        showGrid: true,
        showTooltip: true,
        animationEnabled: true,
        responsiveWidth: '90%',
        containerJustify: 'center',
      };
    case 'desktop':
      return {
        alignment: 'center',
        marginX: 'auto',
        marginY: '16px',
        legendPosition: 'right',
        showGrid: true,
        showTooltip: true,
        animationEnabled: true,
        responsiveWidth: '100%',
        containerJustify: 'center',
      };
    default:
      return {
        alignment: 'center',
        marginX: 'auto',
        marginY: '16px',
        legendPosition: 'right',
        showGrid: true,
        showTooltip: true,
        animationEnabled: true,
        responsiveWidth: '100%',
        containerJustify: 'center',
      };
  }
}

export function getResponsivePieChartSize(screen) {
  switch (screen) {
    case 'mobile':
      return {
        containerMaxWidth: '100%',
        containerMinWidth: '0px',
        height: '300px',
        chartWidth: '100%',
        chartHeight: 300,
      };
    case 'tablet':
      return {
        containerMaxWidth: '500px',
        containerMinWidth: '500px',
        height: '350px',
        chartWidth: '100%',
        chartHeight: 350,
      };
    case 'desktop':
      return {
        containerMaxWidth: '600px',
        containerMinWidth: '600px',
        height: '400px',
        chartWidth: '100%',
        chartHeight: 400,
      };
    default:
      return {
        containerMaxWidth: '600px',
        containerMinWidth: '600px',
        height: '400px',
        chartWidth: '100%',
        chartHeight: 400,
      };
  }
}

export function getResponsiveDataFormat(screen) {
  switch (screen) {
    case 'mobile':
      return {
        numberFormat: 'compact',
        dateFormat: 'short',
        decimalPlaces: 1,
        abbreviateUnits: true,
        showFullLabels: false,
      };
    case 'tablet':
      return {
        numberFormat: 'full',
        dateFormat: 'short',
        decimalPlaces: 2,
        abbreviateUnits: false,
        showFullLabels: true,
      };
    case 'desktop':
      return {
        numberFormat: 'full',
        dateFormat: 'full',
        decimalPlaces: 2,
        abbreviateUnits: false,
        showFullLabels: true,
      };
    default:
      return {
        numberFormat: 'full',
        dateFormat: 'full',
        decimalPlaces: 2,
        abbreviateUnits: false,
        showFullLabels: true,
      };
  }
}

export function getResponsiveTileDisplay(screen) {
  switch (screen) {
    case 'mobile':
      return {
        fieldsPerTile: 2,
        fontSizeLabel: '10px',
        fontSizeValue: '14px',
        fontSizeUnit: '9px',
        valueFormat: 'compact',
        showStatusDot: true,
        showUnit: false,
        showChange: false,
        cardHeight: '100px',
        cardPadding: '12px',
      };
    case 'tablet':
      return {
        fieldsPerTile: 3,
        fontSizeLabel: '11px',
        fontSizeValue: '16px',
        fontSizeUnit: '10px',
        valueFormat: 'full',
        showStatusDot: true,
        showUnit: true,
        showChange: false,
        cardHeight: '110px',
        cardPadding: '14px',
      };
    case 'desktop':
      return {
        fieldsPerTile: 4,
        fontSizeLabel: '12px',
        fontSizeValue: '18px',
        fontSizeUnit: '11px',
        valueFormat: 'full',
        showStatusDot: true,
        showUnit: true,
        showChange: true,
        cardHeight: '120px',
        cardPadding: '16px',
      };
    default:
      return {
        fieldsPerTile: 4,
        fontSizeLabel: '12px',
        fontSizeValue: '18px',
        fontSizeUnit: '11px',
        valueFormat: 'full',
        showStatusDot: true,
        showUnit: true,
        showChange: true,
        cardHeight: '120px',
        cardPadding: '16px',
      };
  }
}

export function formatResponsiveNumber(value, screen, decimals) {
  const config = getResponsiveDataFormat(screen);
 
  if (config.numberFormat === 'compact') {
    if (value >= 1000000) {
      return (value / 1000000).toFixed(decimals || 1) + 'M';
    } else if (value >= 1000) {
      return (value / 1000).toFixed(decimals || 1) + 'K';
    }
    return value.toString();
  }
 
  return value.toLocaleString('en-US', { maximumFractionDigits: decimals || 2 });
}

export function getVisibleTileFields(tileData, screen) {
  const config = getResponsiveTileDataConfig(screen);
  const result = {};
 
  config.showFields.forEach(field => {
    if (tileData.hasOwnProperty(field)) {
      result[field] = tileData[field];
    }
  });
 
  return result;
}

export function getVisibleTableColumns(columnNames, screen) {
  const config = getResponsiveTableColumns(screen);
 
  return columnNames.filter(col =>
    config.visibleColumns.includes(col) &&
    columnNames.indexOf(col) < config.maxColumns
  );
}

export function getSmartVisibleColumns(columnNames, screen) {
  if (screen === 'desktop') {
    return columnNames;
  }
  return getVisibleTableColumns(columnNames, screen);
}

export function getSmartVisibleTileFields(tileData, screen) {
  if (screen === 'desktop') {
    return tileData;
  }
  return getVisibleTileFields(tileData, screen);
}

export function getSmartTileDisplay(screen) {
  if (screen === 'desktop') {
    return {
      fieldsPerTile: 999,
      fontSizeLabel: '12px',
      fontSizeValue: '18px',
      fontSizeUnit: '11px',
      valueFormat: 'full',
      showStatusDot: true,
      showUnit: true,
      showChange: true,
      cardHeight: 'auto',
      cardPadding: '16px',
    };
  }
  return getResponsiveTileDisplay(screen);
}

export function getSmartTableConfig(screen) {
  if (screen === 'desktop') {
    return {
      fontSize: '14px',
      padding: '10px 14px',
      compactMode: false,
      columnsVisible: 999,
    };
  }
  return getResponsiveTable(screen);
}

export function getSmartDataFormat(screen) {
  if (screen === 'desktop') {
    return {
      numberFormat: 'full',
      dateFormat: 'full',
      decimalPlaces: 2,
      abbreviateUnits: false,
      showFullLabels: true,
    };
  }
  return getResponsiveDataFormat(screen);
}

export function getSmartFormattedNumber(value, screen, decimals) {
  const config = getSmartDataFormat(screen);
 
  if (config.numberFormat === 'compact') {
    if (value >= 1000000) {
      return (value / 1000000).toFixed(decimals || 1) + 'M';
    } else if (value >= 1000) {
      return (value / 1000).toFixed(decimals || 1) + 'K';
    }
    return value.toString();
  }
 
  return value.toLocaleString('en-US', { maximumFractionDigits: decimals || 2 });
}

export function getDesktopSidebarWidth(screen) {
  return (screen === 'desktop' || screen === 'tablet') ? '260px' : '180px';
}

export function getCenteredContentStyle(screen) {
  return {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    width: '100vw',
    margin: 0,
    padding: 0,
  };
}
