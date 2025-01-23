import os
import json
from collections import Counter
import asyncio
from openai import AsyncOpenAI
from datetime import datetime


from helper.upload_to_S3 import main as upload_to_S3_main  # Import the function from upload.py


def merge_timelines(data):
    # Combine multiple timeline entries into a single object
    merged_timeline = []
    total_screenshots = 0
    processing_time = "0 seconds"
    last_updated = None

    for entry in data:
        # Add all timeline objects to the merged timeline
        merged_timeline.extend(entry.get("timeline", []))
        # Accumulate total screenshots
        total_screenshots += entry.get("total_screenshots", 0)
        # Use the latest processing time and last_updated timestamp
        processing_time = entry.get("processing_time", processing_time)
        last_updated = entry.get("last_updated", last_updated)

    return {
        "timeline": merged_timeline,
        "total_screenshots": total_screenshots,
        "processing_time": processing_time,
        "last_updated": last_updated
    }


def clean_json_string(json_str):
    # Remove the ```json prefix and ``` suffix if present
    if json_str.startswith("```json\n"):
        json_str = json_str[8:]
    if (json_str.endswith("\n```")):
        json_str = json_str[:-4]
    return json_str


def analyze_timeline_file(file_path):
    # Read the JSON file
    print(f"Analyzing file path : {file_path}")
    with open(file_path, 'r') as file:
        data = json.load(file)
        print(f"Data in json file of timeline : {data}")
        singleData = merge_timelines(data)
        print("z")
        print(f"single data {singleData}")
        timeline_data = singleData.get("timeline", [])  # Get timeline as list, empty list if not found
        print("x")
    # Calculate time interval from first two entries
    time_interval = 5  # default fallback value
    if len(timeline_data) >= 2:
        try:
            time1 = int(timeline_data[0]["time_from_start"][-2:])
            time2 = int(timeline_data[1]["time_from_start"][-2:])
            time_interval = time2 - time1
            print(f"Detected time interval between entries: {time_interval} seconds")
        except (KeyError, TypeError) as e:
            print(f"Warning: Could not calculate time interval, using default - {str(e)}")
    print("c")
    # Initialize counters and lists
    activities = []
    prompts_with_time = []
    print(f"timeline_data : {timeline_data}")
    # Process each timeline entry
    for entry in timeline_data:
        try:
            # Clean and parse the analysis JSON string
            analysis_str = clean_json_string(entry["analysis"])
            analysis = json.loads(analysis_str)
            print("v")
            # Extract activity for counting
            activity = analysis["activity"]
            activities.append(activity)
            print("b")
            # Extract prompts with timestamps
            time_from_start = entry["time_from_start"]
            windows = analysis["open_windows"]
            print("n")
            for window in windows:
                if "prompt" in window and window["prompt"]:  # Only include non-empty prompts
                    prompts_with_time.append({
                        "time_from_start": time_from_start,
                        "prompt": window["prompt"]
                    })
        except Exception as e:
            print(f"Warning: Error processing entry - {str(e)}")
            continue

    # Count activities and multiply by dynamic time interval
    activity_durations = {
        activity: count * time_interval for activity, count in Counter(activities).items()
    }

    # Create final output
    output = {
        "activity_durations": activity_durations,
        "prompts_timeline": prompts_with_time,
        "metadata": {
            "total_screenshots": data.get("total_screenshots"),
            "processing_time": data.get("processing_time"),
            "last_updated": data.get("last_updated"),
            "time_interval": time_interval
        }
    }

    return output


def save_prompts_timeline(file_path, output):
    """Save prompts timeline to a separate file with _prompts suffix"""
    # Get the file name without extension
    base_name = file_path.rsplit('.', 1)[0]
    prompts_file = f"{base_name}_prompts.json"
    
    # Extract just the prompts timeline
    prompts_data = {
        "prompts_timeline": output["prompts_timeline"],
        "metadata": output["metadata"]
    }
    
    # Save to file
    with open(prompts_file, 'w') as f:
        json.dump(prompts_data, f, indent=2)
    
    print(f"Prompts timeline saved to {prompts_file}")


def save_activity_durations(file_path, output, assignment_id, user_id, submission_id):
    """Save activity durations to a separate file with _activities suffix"""
    # Print raw data in seconds
    print("\nRaw activity durations (in seconds):")
    sorted_raw = sorted(output["activity_durations"].items(), key=lambda x: x[1], reverse=True)
    for activity, duration in sorted_raw:
        print(f"{activity}: {duration} seconds")
    print()  # Empty line for better readability
    
    # Get the file name without extension
    base_name = file_path.rsplit('.', 1)[0]
    activities_file = f"/tmp/timeline_analysis/{submission_id}/{assignment_id}_{user_id}_time_spent.json"
    
    # Convert seconds to minutes for all activities
    activity_minutes = {
        activity: round(duration / 60, 2) 
        for activity, duration in output["activity_durations"].items()
    }
    
    # Sort activities by duration in descending order
    sorted_activities = sorted(activity_minutes.items(), key=lambda x: x[1], reverse=True)
    
    # Take top 5 activities and sum the rest into "Other"
    top_activities = dict(sorted_activities[:5])
    other_duration = sum(duration for _, duration in sorted_activities[5:])
    
    # Add "Other" category if there are more than 5 activities
    if other_duration > 0:
        top_activities["Other"] = round(other_duration, 2)
    
    activity_data = {
        "activity_durations": top_activities,
        "metadata": output["metadata"]
    }
    
    # Add unit information to metadata
    activity_data["metadata"]["duration_unit"] = "minutes"
    
    # Save to file
    with open(activities_file, 'w') as f:
        json.dump(activity_data, f, indent=2)
    
    print(f"Activity durations saved to {activities_file}")


def save_raw_prompts(file_path, output, assignment_id, user_id, submission_id):
    """Save raw prompts timeline without any processing"""
    base_name = file_path.rsplit('.', 1)[0]
    raw_prompts_file = f"/tmp/timeline_analysis/{submission_id}/{assignment_id}_{user_id}_raw_prompts.json"
    
    # Extract just the prompts timeline without any processing
    raw_prompts_data = {
        "prompts_timeline": output["prompts_timeline"],
        "metadata": output["metadata"]
    }
    
    # Save to file
    with open(raw_prompts_file, 'w') as f:
        json.dump(raw_prompts_data, f, indent=2)
    
    print(f"Raw prompts timeline saved to {raw_prompts_file}")


def save_app_actions(file_path, output, assignment_id, user_id, submission_id):
    """Save app and action timeline without consecutive duplicates"""
    base_name = file_path.rsplit('.', 1)[0]
    app_actions_file = f"/tmp/timeline_analysis/{submission_id}/{assignment_id}_{user_id}_app_actions.json"
    
    app_actions_timeline = []
    previous_entry = None
    
    # Read the original timeline data again
    with open(file_path, 'r') as file:
        data = json.load(file)
        timeline_data = data.get("timeline", [])
    
    # Process through the timeline data
    for entry in timeline_data:
        try:
            time = entry["time_from_start"]
            analysis_str = clean_json_string(entry["analysis"])
            analysis = json.loads(analysis_str)
            windows = analysis["open_windows"]
            
            for window in windows:
                current_entry = {
                    "time": time,
                    "app": window.get("app", ""),
                    "action": window.get("action", "")
                }
                
                # Only add if different from previous entry
                if previous_entry is None or (
                    previous_entry["app"] != current_entry["app"] or 
                    previous_entry["action"] != current_entry["action"]
                ):
                    app_actions_timeline.append(current_entry)
                    previous_entry = current_entry
        except Exception as e:
            print(f"Warning: Error processing entry for app actions - {str(e)}")
            continue
    
    # Prepare output data
    app_actions_data = {
        "app_actions_timeline": app_actions_timeline,
        "metadata": output["metadata"]
    }
    
    # Save to file
    with open(app_actions_file, 'w') as f:
        json.dump(app_actions_data, f, indent=2)
    
    print(f"App actions timeline saved to {app_actions_file}")


async def merge_prompts_with_gpt4(prompts_data: dict, api_key: str) -> dict:
    """Merge similar prompts using GPT-4V API"""
    client = AsyncOpenAI(api_key=api_key)
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": f"""Here is a list of prompts user asked AI tools extracted from user's screenshots every 5/10 secs. 
                    When we are taking screenshots sometimes we don't see entire text because of limited text box size (text can overflow) 
                    and the user could be editing their prompt in between, your task is to merge such prompts and figure out the prompt 
                    user typed. You also need to mention the time for each prompt, which still keeping all distinct prompts as sperate entries. 
                    Output JSON in same format as input json:
                    
                    {json.dumps(prompts_data, indent=2)}"""
                }
            ],
            max_tokens=10000,
            temperature=0
        )
        
        merged_data = json.loads(response.choices[0].message.content)
        print ("Merged prompts successfully")
        return merged_data
        
    except Exception as e:
        print(f"Error in merging prompts: {str(e)}")
        return prompts_data


async def analyze_app_actions_with_o1(app_actions_data: dict, api_key: str) -> dict:
    """Analyze app actions timeline using GPT-4 to merge similar activities"""
    client = AsyncOpenAI(api_key=api_key)
    
    try:
        response = await client.chat.completions.create(
            model="o1-preview",
            messages=[
                {
                    "role": "user",
                    "content": f"""There's a candidate whose time series activity log is input. Your task is to merge logically similar activties together and output in following format. For coding activities, you can split based on each bug or issue user faced. Fixing each bug/issue may have required the user to do multiple things like search on AI, code, test and then search again, in that case those can be merged because they are for same issue.

Output format
[{{
activity: <1 line summary of combined activty. If it's a bug include important info like they fixed it by reading documentation, asking ChatGPT, etc.>,
time: <Start time of the activty>,
details: <Bullet point List of things the user did during this activity>,
}}, {{...}}, {{..}}]

Input:
{json.dumps(app_actions_data, indent=2)}"""
                }
            ],
        )
        analyzed_data = json.loads(response.choices[0].message.content[8:-4])
    
                
        print("App actions analysis completed successfully")
        return analyzed_data
        
    except Exception as e:
        print(f"Error in analyzing app actions: {str(e)}")
        return app_actions_data


async def main(submission_id, assignment_id, user_id):
    # Configuration
    file_path = f"/tmp/analysis/{submission_id}.json"
    base_name = f"{submission_id}.json"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Create a new folder for the `submission_id`
    submission_folder = f"/tmp/timeline_analysis/{submission_id}"
    os.makedirs(submission_folder, exist_ok=True)

    # Analyze the timeline file
    try:
        analysis_output = analyze_timeline_file(file_path)
    except Exception as e:
        print(f"Error analyzing timeline file: {str(e)}")
        return

    # Save processed outputs
    save_prompts_timeline(file_path, analysis_output)
    save_activity_durations(file_path, analysis_output, assignment_id, user_id, submission_id)
    save_raw_prompts(file_path, analysis_output, assignment_id, user_id, submission_id)
    save_app_actions(file_path, analysis_output, assignment_id, user_id, submission_id)

    # Merge prompts using GPT-4 API
    try:
        prompts_file_path = f"{submission_folder}/{assignment_id}_{user_id}_raw_prompts.json"
        with open(prompts_file_path, "r") as f:
            raw_prompts_data = json.load(f)
        
        merged_prompts = await merge_prompts_with_gpt4(raw_prompts_data, OPENAI_API_KEY)
        
        # Save merged prompts
        merged_prompts_file = f"{submission_folder}/{assignment_id}_{user_id}_ai_prompts.json"
        with open(merged_prompts_file, "w") as f:
            json.dump(merged_prompts, f, indent=2)
        print(f"Merged prompts saved to {merged_prompts_file}")
    except Exception as e:
        print(f"Error merging prompts: {str(e)}")

    # Analyze app actions timeline using GPT
    try:
        app_actions_file_path = f"{submission_folder}/{assignment_id}_{user_id}_app_actions.json"
        with open(app_actions_file_path, "r") as f:
            app_actions_data = json.load(f)

        analyzed_app_actions = await analyze_app_actions_with_o1(app_actions_data, OPENAI_API_KEY)

        # Save analyzed app actions
        analyzed_app_actions_file = f"{submission_folder}/{assignment_id}_{user_id}_timeline_summary.json"
        with open(analyzed_app_actions_file, "w") as f:
            json.dump(analyzed_app_actions, f, indent=2)
        print(f"Analyzed app actions saved to {analyzed_app_actions_file}")
    except Exception as e:
        print(f"Error analyzing app actions: {str(e)}")

    # Upload all results to S3
    try:
        await upload_to_S3_main(submission_id)
        print(f"All results uploaded to S3 from {submission_folder}")
    except Exception as e:
        print(f"Error uploading results to S3: {str(e)}")

    print("Processing completed successfully.")

