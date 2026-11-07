KEY_OPTIONS = ["cdrm", "manual"]
DYNAMIC_OPTIONS = [
    "digitalcriminals",
    "manual",
    "generic",
    "datawhores",
    "xagler",
    "rafa",
]
# other names accepted for a dynamic rule, and the rule each one picks
DYNAMIC_ALIASES = {
    "dc": "digitalcriminals",
    "digital": "digitalcriminals",
    "digitals": "digitalcriminals",
    "digitalcriminal": "digitalcriminals",
}
# the name the config menus list and save for a rule, when it isn't the
# rule's own name; "digital" is also the default in a new config.json
DYNAMIC_MENU_NAMES = {
    "digitalcriminals": "digital",
}


def dynamic_menu_name(rule):
    """The name the config menus list and save for a rule or any of its names."""
    rule = str(rule or "").lower()
    rule = DYNAMIC_ALIASES.get(rule, rule)
    return DYNAMIC_MENU_NAMES.get(rule, rule)

MEDIA_ALIASES = {
    "photo": "images",
    "photos": "images",
    "image": "images",
    "images": "images",
    "audio": "audios",
    "audios": "audios",
    "video": "videos",
    "videos": "videos",
    "gif": "videos",
    "gifs": "videos",
}