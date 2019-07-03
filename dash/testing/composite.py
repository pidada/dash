from dash.testing.browser import Browser


class DashComposite(Browser):
    def __init__(
        self,
        server,
        browser,
        headless=False,
        options=None,
        remote=None,
        wait_timeout=10,
    ):
        super(DashComposite, self).__init__(
            browser, headless, options, remote, wait_timeout
        )
        self.server = server

    def start_server(self, app, **kwargs):
        """start the local server with app"""

        # start server with app and pass Dash arguments
        self.server(app, **kwargs)

        # set the default server_url, it implicitly call wait_for_page
        self.server_url = self.server.url
