import os
import time
import base64
import boto3
from time import sleep
import asyncio

import re
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from openai import AsyncOpenAI
from helper.timeline_analysis import main as timeline_analysis_main


def extract_and_convert_to_local(filename, offset_hours, offset_minutes):
    # Define the regex pattern to match the date, time, and milliseconds
    pattern = r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{3})"
    match = re.search(pattern, filename)
    
    if match:
        # Extract the matched groups, including milliseconds
        year, month, day, hour, minute, second, millisecond = map(int, match.groups())
        
        # Create a datetime object in UTC, including milliseconds
        utc_time = datetime(
            year, month, day, hour, minute, second, millisecond * 1000, tzinfo=timezone.utc
        )
        
        # Convert to the local timezone
        local_offset = timedelta(hours=offset_hours, minutes=offset_minutes)
        local_timezone = timezone(local_offset)
        local_time = utc_time.astimezone(local_timezone)
        
        # Format the local time to HH:MM:SS
        return local_time.strftime("%H:%M:%S")
    else:
        return None


# AWS S3 Download Function
# def download_images_from_s3(bucket_name: str, folder_path: str, prefix: str, s3_client=None):
#     """
#     Downloads images from a specific folder in an S3 bucket to the specified local folder.
#     """
#     if s3_client is None:
#         s3_client = boto3.client('s3')  # Initialize the S3 client
    
#     print(f"Fetching images from bucket: {bucket_name}, prefix: {prefix}")
    
#     try:
#         response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
#     except Exception as e:
#         print(f"Error listing objects: {e}")
#         return

#     if 'Contents' not in response:
#         print(f"No files found with prefix {prefix} in bucket {bucket_name}")
#         return

#     os.makedirs(folder_path, exist_ok=True)

#     for item in response['Contents']:
#         file_key = item['Key']
#         if file_key.endswith('.jpg') and file_key.startswith(prefix):
#             file_name = os.path.join(folder_path, os.path.basename(file_key))
#             try:
#                 s3_client.download_file(bucket_name, file_key, file_name)
#                 print(f"Downloaded: {file_name}")
#             except Exception as e:
#                 print(f"Error downloading {file_key}: {e}")

def download_images_from_s3(bucket_name: str, folder_path: str, prefix: str, start_no: int, end_no: int, s3_client=None):
    """
    Downloads a specific range of images from a folder in an S3 bucket to the specified local folder.
    Downloads images based on a range defined by start_no and end_no (inclusive).

    :param bucket_name: Name of the S3 bucket.
    :param folder_path: Local folder where images will be downloaded.
    :param prefix: Prefix in the S3 bucket to filter files.
    :param start_no: The starting number (1-based index) of the range of images to download.
    :param end_no: The ending number (1-based index) of the range of images to download.
    :param s3_client: S3 client object (optional).
    """
    if s3_client is None:
        s3_client = boto3.client('s3')  # Initialize the S3 client
    
    print(f"Fetching images from bucket: {bucket_name}, prefix: {prefix}")
    
    try:
        # List objects in the bucket with the specified prefix
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    except Exception as e:
        print(f"Error listing objects: {e}")
        return

    if 'Contents' not in response:
        print(f"No files found with prefix {prefix} in bucket {bucket_name}")
        return

    # Filter only .jpg files and sort by key
    images = [item['Key'] for item in response['Contents'] if item['Key'].endswith('.jpg') and item['Key'].startswith(prefix)]
    images.sort()  # Ensure the sequence is consistent with S3 order

    # Select the range of images to download
    selected_images = images[start_no - 1:end_no]  # 1-based index adjustment
    if not selected_images:
        print(f"No images found in the specified range ({start_no} to {end_no}).")
        return

    os.makedirs(folder_path, exist_ok=True)

    for file_key in selected_images:
        file_name = os.path.join(folder_path, os.path.basename(file_key))
        try:
            s3_client.download_file(bucket_name, file_key, file_name)
            print(f"Downloaded: {file_name}")
        except Exception as e:
            print(f"Error downloading {file_key}: {e}")


def encode_image(image_path: str) -> str:
    """Convert image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def extract_time_from_filename(filename: str) -> str:
    """Extract the time information from filename (format: frame_HH-MM-SS)"""
    match = re.search(r'frame_(\d+-\d+-\d+)', filename)
    if match:
        time_str = match.group(1)
        hours, minutes, seconds = map(int, time_str.split('-'))
        return str(timedelta(hours=hours, minutes=minutes, seconds=seconds))
    return None


async def analyze_single_image(
        client: AsyncOpenAI,
        image_path: str,
        image_file: str,
        semaphore: asyncio.Semaphore,
        delay=0,
) -> Dict:
    """Analyze a single image using OpenAI API with rate limiting"""
    #sleep(delay)
    await asyncio.sleep(delay)

    async with semaphore:  # Control concurrent requests
        try:
            time_from_start = extract_and_convert_to_local(image_file, 5, 30)
            print("1")
            base64_image = encode_image(image_path)
            print("2")
            print(f"Analyzing image: {image_file} at {image_path}")
            response = await client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Create an array of json object

activity: <First, only look at the active window or active tab i.e. where the user's cursor or keyboard typing is active. which one of the following best describes the work user is doing on the active window. Pick any one of the following "Coding", "AI Copilot in IDE" (double check user must be in a code editor (native application), and not on any website that looks like code editor), "Reading Documentation" (must be an official documentation, make a guess based on url if url or page header looks like one for an official documentation), "Reading Web articles/documents" (for articles, blogs, PDFs or report on other webpages), "Reading Stackoverflow", "Watching video tutorial", "Interacting with AI Chatbot" (Select this if user is on an AI website like chatgpt, bolt.new, lovable.dev, claude, gemini, perplexity), "Testing" (select if user is running their code in command line or opening a website created by them for example on localhost, mstunnels, ngrok), "Creating Document" (word, excel, powerpoint), "Reading code in GitHub", "Google Search", "Other". You can pick only one category from double quotes, and do not make a category of your own.>
open_windows: [
{
app: <Find out which app or web app the user is using>,
action: <What is the user doing on  this app, answer based on what you see the contents of the app, include as many details as you can in 1 line>,
prompt: <copy paste what user is asking the AI/Search engine to do. Only populate this field if you can see what the user has typed into a text box (and its not a textbox hint like "How can bolt help you today?" or "Edit code (Ctrl+I), @ to mention"). You should be 100% confident that for AI copilots in code editors,  Whatever you are copy pasting here must have been typed into a text box by a human (You know if it was written by human if it starts with small characters, improper grammar or punctuation use).>,
},
{...},
{...}
]

If the user has multiple windows open with split screen, you can return one object for each window you see. If there's one primary window and others are in background you can skip returning details about the windows in background. Only return multiple when user is using split screen. Ignore the user webcam image overlays if any present."""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high",
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0
            )
            print("3")
            analysis = response.choices[0].message.content
            print("4")
            print(time_from_start, analysis)
            print("5")

            return {
                "time_from_start": time_from_start,
                "analysis": analysis,
            }

            

        except Exception as e:
            print(f"Error processing {image_file}: {str(e)}")
            return {
                "time_from_start": time_from_start,
                "filename": image_file,
                "error": str(e),
                "processed_at": datetime.now().isoformat()
            }


async def analyze_screenshots(
    folder_path: str, 
    api_key: str, 
    results_file: str, 
    image_range: List[int] = None,
    max_concurrent: int = 3
):
    """
    Analyze screenshots concurrently using OpenAI's Vision API

    Args:
        folder_path (str): Path to the folder containing screenshots
        api_key (str): OpenAI API key
        results_file (str): Path to save the results JSON file
        image_range (List[int]): Range of images to process [start, end]
        max_concurrent (int): Maximum number of concurrent API calls
    """
    # Initialize OpenAI client
    client = AsyncOpenAI(api_key=api_key)

    # Get all jpg files from the folder
    images = [f for f in os.listdir(folder_path) if f.endswith('.jpg')]
    images.sort()
    print(images)

    # Create semaphore for rate limiting
    semaphore = asyncio.Semaphore(max_concurrent)

  

    tasks = []
    for num, image_file in enumerate(images):
        if image_range and (num < image_range[0] or num > image_range[1]): 
            continue
        image_path = os.path.join(folder_path, image_file)
        # task = await analyze_single_image(client, image_path, image_file, semaphore)
        # tasks.append(task)

        tasks.append(
            asyncio.create_task(
                analyze_single_image(client, image_path, image_file, semaphore)
            )
        )


    # Process images concurrently
    start_time = time.time()
    print(f"Starting analysis of {len(images)} screenshots...")

    #results = await asyncio.gather(*tasks)
    results = await asyncio.gather(*tasks, return_exceptions=True)


    # Sort results by timestamp
    timeline = sorted(results, key=lambda x: x['time_from_start'] if x['time_from_start'] else '')

    # Save results
    with open(results_file, 'w') as f:
        json.dump({
            "timeline": timeline,
            "total_screenshots": len(images),
            "processing_time": f"{time.time() - start_time:.2f} seconds",
            "last_updated": datetime.now().isoformat()
        }, f, indent=4)

    print(f"\nAnalysis complete in {time.time() - start_time:.2f} seconds")
    print(f"Results saved to {results_file}")

    return timeline


async def main(submission_id, assignment_id, user_id, start_no, end_no):
    if not submission_id:
        raise ValueError("submission_id is required but not provided.")

    try:
        start_no = int(start_no)
        end_no = int(end_no)
    except ValueError:
        raise ValueError("start_no and end_no must be valid integers.")

    print(f"This is start: {start_no}")
    print(f"This is end: {end_no}")
    # Configuration
    ASSIGNMENT_ID=submission_id
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Replace with your actual API key
    SCREENSHOTS_FOLDER = f"/tmp/screenshots/{ASSIGNMENT_ID}"
    RESULTS_FILE = f"/tmp/analysis/{ASSIGNMENT_ID}.json"
    IMAGE_RANGE = [0, 2200]  # Specify which images to process (adjust as needed)
    MAX_CONCURRENT_REQUESTS = 60  # Adjust based on your API limits
    PREFIX=f"screenshots/{ASSIGNMENT_ID}"
    BUCKET_NAME = os.getenv("BUCKET_NAME")  # Replace with your S3 bucket name

    os.makedirs(SCREENSHOTS_FOLDER, exist_ok=True)  # Creates /tmp/screenshots/example_assignment if it doesn't exist
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)  # Creates /tmp/analysis if it doesn't exist
    print(f"submission_id: {submission_id}")
    print(f"SCREENSHOTS_FOLDER: {SCREENSHOTS_FOLDER}")
    print(f"BUCKET_NAME: {BUCKET_NAME}")

    # Download images from S3 before starting analysis
    download_images_from_s3(BUCKET_NAME, SCREENSHOTS_FOLDER, PREFIX, start_no, end_no)


    # Run analysis after downloading images
    try:
        timeline = await analyze_screenshots(
            SCREENSHOTS_FOLDER,
            OPENAI_API_KEY,
            RESULTS_FILE,
            IMAGE_RANGE,
            MAX_CONCURRENT_REQUESTS
        )
    except Exception as e:
        print(f"Error analyzing screenshots: {e}")
        timeline = []  # In case of failure, ensure you still return an empty timeline

    try:
        await timeline_analysis_main(submission_id, assignment_id, user_id)
    except Exception as e:
        print(f"Error during timeline analysis: {e}")


# if __name__ == "__main__":
#     # This ensures your `main()` function is run within an event loop
#     asyncio.run(main(submission_id, assignment_id, user_id))

