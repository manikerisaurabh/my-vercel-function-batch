import os
import time
import base64
import boto3

import re
import json
import trio
from datetime import datetime, timezone, timedelta
from time import sleep
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
def download_images_from_s3(bucket_name: str, folder_path: str, prefix: str, s3_client=None):
    """
    Downloads images from a specific folder in an S3 bucket to the specified local folder.
    
    Args:
        bucket_name (str): S3 bucket name
        folder_path (str): Local folder to save images
        s3_client: boto3 S3 client (can be passed as an argument or default to a new client)
    """
    if s3_client is None:
        s3_client = boto3.client('s3')  # Initialize the S3 client
    
    # List objects in the S3 bucket with a prefix matching the folder path
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    
    if 'Contents' not in response:
        print("Looking for images in folder:", os.path.abspath(folder_path))
        return
    
    os.makedirs(folder_path, exist_ok=True)  # Ensure the folder exists

    for item in response['Contents']:
        # Check if the object is an image and if its key starts with the specified folder path
        file_key = item['Key']
        if file_key.endswith('.jpg') and file_key.startswith(folder_path):  # Only download jpg images
            file_name = os.path.join(folder_path, os.path.basename(file_key))
            s3_client.download_file(bucket_name, file_key, file_name)
            print(f"Downloaded {file_name}")


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

    # Create semaphore for rate limiting
    semaphore = trio.Semaphore(max_concurrent)

    results = []
    start_time = time.time()
    print(f"Starting analysis of {len(images)} screenshots...")

    # Use trio.Nursery for concurrency
    async with trio.open_nursery() as nursery:
        for num, image_file in enumerate(images):
            if image_range and (num < image_range[0] or num > image_range[1]): 
                continue
            image_path = os.path.join(folder_path, image_file)
            nursery.start_soon(
                analyze_and_collect, client, image_path, image_file, semaphore, results
            )

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

    # Create semaphore for rate limiting
    semaphore = trio.Semaphore(max_concurrent)

    # Create tasks for all images
    tasks = []
    for num, image_file in enumerate(images):
        if image_range and (num < image_range[0] or num > image_range[1]): 
            continue
        image_path = os.path.join(folder_path, image_file)
        task = analyze_single_image(client, image_path, image_file, semaphore)
        tasks.append(task)

    # Process images concurrently using trio
    start_time = time.time()
    print(f"Starting analysis of {len(images)} screenshots...")

    results = await trio.gather(*tasks)

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


# Main entry point of the script
async def main(submission_id, assignment_id, user_id):
    if not submission_id:
        raise ValueError("submission_id is required but not provided.")

    
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
    download_images_from_s3(BUCKET_NAME, SCREENSHOTS_FOLDER, PREFIX)

    # Run analysis after downloading images
    timeline = await analyze_screenshots(
        SCREENSHOTS_FOLDER,
        OPENAI_API_KEY,
        RESULTS_FILE,
        IMAGE_RANGE,
        MAX_CONCURRENT_REQUESTS
    )   
    await timeline_analysis_main(submission_id, assignment_id, user_id)

if __name__ == "__main__":
    trio.run(main)
