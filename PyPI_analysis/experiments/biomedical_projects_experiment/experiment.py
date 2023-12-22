import json
import os
import boto3
from botocore.exceptions import ClientError
import shutil
from git.exc import GitCommandError
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, wait

from PyPI_analysis.download_and_analyze import pypi_analysis

json_file_path = "repositories.json"
client = boto3.client("s3")
bucket = "fawltydeps-tweag"


def upload_to_aws(local_folder, s3_location):
    for root, dirs, files in os.walk(local_folder):
        for filename in files:
            if (
                not filename.endswith(".png")
                and not filename.endswith(".pdf")
                and not filename.endswith(".xml")
                and not filename.endswith(".mp4")
            ):
                local_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_path, local_folder)
                s3_path = os.path.join(s3_location, relative_path)
                if os.path.exists(local_path):
                    try:
                        client.upload_file(local_path, bucket, s3_path)
                    except ClientError as e:
                        print(f"Client error {e} occurs.")


def do_analysis(repo_url, repo_name, save_location):
    repository = pypi_analysis(repo_url, repo_name, save_location)
    if not os.path.exists(save_location):
        try:
            repository.clone_repo()
        except GitCommandError:
            print(f"Git clone error for {repo_name}.")
            if os.path.exists(save_location):
                shutil.rmtree(save_location)
            return

    upload_to_aws(save_location, "pypi_analysis/data/" + repo_name)

    repository.analysis()

    if os.path.exists("results/" + repo_name + ".json"):
        try:
            client.upload_file(
                "results/" + repo_name + ".json",
                bucket,
                "pypi_analysis/results/" + repo_name + ".json",
            )
        except ClientError as e:
            print(f"Client error {e} occurs.")
    else:
        print(f"Cannot find analysis results of {repo_name}!")

    if os.path.exists(save_location):
        shutil.rmtree(save_location)


with open(json_file_path, "r") as file:
    repositories = json.load(file)

tasks = []
with tqdm(
    desc="Running FawltyDeps analysis",
    total=len(repositories),
    position=0,
    leave=True,
) as pbar:
    with ThreadPoolExecutor() as ex:
        for repo in repositories:
            repo_url = "https://:@" + repo["domain"] + "/" + repo["repository"] + ".git"
            repo_name = repo["repository"].split("/")[-1]
            save_location = "temp/" + repo_name

            result = ex.submit(do_analysis, repo_url, repo_name, save_location)
            result.add_done_callback(lambda _x: pbar.update())
            tasks.append(result)
        wait(tasks)