import logging

class BasePlugin:
    """
    Base class for all OF-Scraper plugins.
    Developers should inherit from this class and implement the desired hooks.
    """

    def __init__(self, metadata: dict, plugin_dir: str):
        self.metadata = metadata
        self.plugin_dir = plugin_dir
        self.log = logging.getLogger(f"ofscraper_plugin.{metadata.get('name', 'unknown')}")

    def on_load(self):
        """Called immediately after the plugin is instantiated."""
        pass

    def on_ui_setup(self, main_window):
        """Called when the PyQt6 GUI layout is initialized."""
        pass

    def on_scrape_start(self, config, models):
        """Called before the main scraper loop begins. Should return the models list (possibly modified)."""
        return models

    def on_item_downloaded(self, item_data, file_path):
        """Called immediately after a media item is saved to disk."""
        pass

    def on_scrape_complete(self, stats):
        """Called when a scraping session finishes completely."""
        pass

    def on_unload(self):
        """Called when the application closes or plugin is disabled."""
        pass
