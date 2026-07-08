class BotSpottedError(Exception):
    def __init__(self, html: str):
        self.detail: str = "The instance was spotted by cloudflare."
        self.html: str = html
        super().__init__("spotted by anti bot")
