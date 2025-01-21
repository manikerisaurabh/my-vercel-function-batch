from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from helper.entry import main  # Import the main function
import asyncio
import json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse query parameters
        query = urlparse(self.path).query
        params = parse_qs(query)

        # Extract parameters
        submission_id = params.get('submission_id', [None])[0]
        assignment_id = params.get('assignment_id', [None])[0]
        user_id = params.get('user_id', [None])[0]
        start_no = params.get('start_no', [None])[0]
        end_no = params.get('end_no', [None])[0]

        # Execute the `main` function asynchronously
        try:
            response_message = asyncio.run(
                self.execute_main(submission_id, assignment_id, user_id, start_no, end_no)
            )
            status_code = 200  # Success
        except Exception as e:
            response_message = {"status": "error", "message": f"Error occurred: {str(e)}"}
            status_code = 500  # Internal Server Error

        # Send response
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_message).encode("utf-8"))

    async def execute_main(self, submission_id, assignment_id, user_id, start_no, end_no):
        """
        Executes the `main` function from temp.py and returns a response message.
        """
        try:
            # Call the main function with the necessary parameters
            await main(submission_id, assignment_id, user_id, start_no, end_no)
            return {"status": "success", "message": "Main function executed successfully."}
        except Exception as e:
            raise Exception(f"Main function execution failed: {str(e)}")
