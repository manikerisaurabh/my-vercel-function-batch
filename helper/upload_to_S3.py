import os
import boto3
import shutil
from botocore.exceptions import NoCredentialsError, ClientError


# AWS S3 Configuration
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
BUCKET_NAME = "authcast-assignments"  # Correct bucket name
FOLDER_NAME = "analysis"
LOCAL_FOLDER = "timeline_analysis"

# Initialize S3 client with credentials
s3 = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

def upload_files_to_s3(submission_id):
    LOCAL_FOLDER = f"timeline_analysis/{submission_id}"
    try:
        # Iterate through all files in the specified local folder
        for root, dirs, files in os.walk(LOCAL_FOLDER):
            for file in files:
                if file.endswith(".json"):
                    local_file_path = os.path.join(root, file)
                    s3_key = f"{FOLDER_NAME}/{file}"

                    try:
                        # Upload the file to S3
                        s3.upload_file(local_file_path, BUCKET_NAME, s3_key)
                        print(f"Uploaded: {local_file_path} -> s3://{BUCKET_NAME}/{s3_key}")
                    except ClientError as e:
                        print(f"Failed to upload {local_file_path} to s3://{BUCKET_NAME}/{s3_key}: {e}")

        # After uploading all files, delete local JSON files
        delete_local_json_files(submission_id)

    except NoCredentialsError:
        print("AWS credentials not found. Please configure them correctly.")
    except Exception as e:
        print(f"An error occurred: {e}")

def delete_local_json_files(submission_id):
    # Paths of the directories and file to delete
    dirs_to_delete = [
        f"screenshots/{submission_id}",
        f"timeline_analysis/{submission_id}",
    ]
    file_to_delete = f"analysis/{submission_id}.json"

    # Delete JSON files in the directories
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
            # Remove the directory itself if it's empty
            try:
                shutil.rmtree(dir_path)
                print(f"Removed directory: {dir_path}")
            except Exception as e:
                print(f"Failed to remove directory {dir_path}: {e}")

    # Delete the single JSON file
    if os.path.exists(file_to_delete):
        try:
            os.remove(file_to_delete)
            print(f"Deleted: {file_to_delete}")
        except Exception as e:
            print(f"Failed to delete {file_to_delete}: {e}")

async def main(submission_id): 
    upload_files_to_s3(submission_id)