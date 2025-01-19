import trio
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from helper.entry import main  # Import the main function from temp.py


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse query parameters
        query = urlparse(self.path).query
        params = parse_qs(query)

        # Extract parameters
        submission_id = params.get('submission_id', [None])[0]
        assignment_id = params.get('assignment_id', [None])[0]
        user_id = params.get('user_id', [None])[0]

        # Run the Trio event loop
        response_message = trio.run(
            self.execute_main, submission_id, assignment_id, user_id
        )

        # Send response
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(response_message.encode("utf-8"))
        return

    async def execute_main(self, submission_id, assignment_id, user_id):
        """
        Executes the `main` function from temp.py and returns a response message.
        """
        try:
            # Call the main function with the necessary parameters
            await main(submission_id, assignment_id, user_id)
            return "Successfully executed the main function from temp.py"
        except Exception as e:
            return f"Error occurred while executing main: {str(e)}"
