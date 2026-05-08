import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "domain_rules.yaml"


def load_domain_rules():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


DOMAIN_RULES = load_domain_rules()


def get_domain_config(domain_key: str):
    return DOMAIN_RULES.get(domain_key, {})


def get_all_domain_keys():
    return list(DOMAIN_RULES.keys())