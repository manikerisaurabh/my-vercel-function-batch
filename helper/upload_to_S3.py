import os
import shutil
import aiofiles
import asyncio
import aioboto3
from botocore.exceptions import NoCredentialsError, ClientError

# AWS S3 Configuration
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")

# Bucket name and folder configuration
BUCKET_NAME = os.getenv("BUCKET_NAME") or "authcast-assignments"
FOLDER_NAME = "analysis"

# Function to upload file to S3
async def upload_file_to_s3(s3_client, local_file_path, s3_key):
    try:
        print(f"local file path : {local_file_path}")
        print(f"bucekt : {BUCKET_NAME}")
        print(f"folder : {FOLDER_NAME}")
        # Open file asynchronously using aiofiles
        async with aiofiles.open(local_file_path, 'rb') as file:
            # Upload the file asynchronously
            print("a")
            await s3_client.put_object(Bucket=BUCKET_NAME, Key=s3_key, Body=file)
            print(f"Uploaded: {local_file_path} -> s3://{BUCKET_NAME}/{s3_key}")
    except ClientError as e:
        print(f"Failed to upload {local_file_path} to s3://{BUCKET_NAME}/{s3_key}: {e}")
    except Exception as e:
        print(f"An error occurred during upload of {local_file_path}: {e}")

# Function to upload multiple files asynchronously
async def upload_files_to_s3(submission_id):
    LOCAL_FOLDER = f"/tmp/timeline_analysis/{submission_id}"
    print(f"Submission ID: {submission_id}")
    print(f"Local folder: {LOCAL_FOLDER}")

    try:
        # Create an S3 client asynchronously with aioboto3
        async with aioboto3.Session().client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            region_name=AWS_REGION
        ) as s3_client:
            tasks = []
            
            # Iterate through all files in the local folder
            for root, dirs, files in os.walk(LOCAL_FOLDER):
                for file in files:
                    if file.endswith(".json"):
                        local_file_path = os.path.join(root, file)
                        s3_key = f"{FOLDER_NAME}/{file}"
                        # Schedule the upload task
                        tasks.append(upload_file_to_s3(s3_client, local_file_path, s3_key))

            # Execute all tasks asynchronously
            if tasks:
                await asyncio.gather(*tasks)

        # After uploading all files, delete local JSON files
        await delete_local_json_files(submission_id)

    except NoCredentialsError:
        print("AWS credentials not found. Please configure them correctly.")
    except Exception as e:
        print(f"An error occurred during S3 upload: {e}")

# Function to delete local JSON files after upload
async def delete_local_json_files(submission_id):
    dirs_to_delete = [
        f"/tmp/screenshots/{submission_id}",
        f"/tmp/timeline_analysis/{submission_id}",
    ]
    file_to_delete = f"/tmp/analysis/{submission_id}.json"

    try:
        # Delete files in directories
        for dir_path in dirs_to_delete:
            if os.path.exists(dir_path):
                for root, dirs, files in os.walk(dir_path):
                    for file in files:
                        if file.endswith(".json"):
                            file_path = os.path.join(root, file)
                            try:
                                os.remove(file_path)
                                print(f"Deleted: {file_path}")
                            except Exception as e:
                                print(f"Failed to delete {file_path}: {e}")
                # Remove the directory if empty
                try:
                    shutil.rmtree(dir_path)
                    print(f"Removed directory: {dir_path}")
                except Exception as e:
                    print(f"Failed to remove directory {dir_path}: {e}")

        # Delete the single JSON file
        if os.path.exists(file_to_delete):
            os.remove(file_to_delete)
            print(f"Deleted: {file_to_delete}")
        else:
            print(f"File {file_to_delete} does not exist.")

    except Exception as e:
        print(f"An error occurred during file deletion: {e}")

# Main entry point to start the process
async def main(submission_id):
    print(f"Submission ID in main of upload_to_S3: {submission_id}")
    await upload_files_to_s3(submission_id)

# Example of how to call the main function with a specific submission_id:
