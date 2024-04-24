import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, wait

import boto3
from botocore.exceptions import ClientError
from git.exc import GitCommandError
from tqdm import tqdm

from PyPI_analysis.download_and_analyze import pypi_analysis

json_file_path = "pypi_repositories.json"
client = boto3.client("s3")
bucket = "fawltydeps-tweag"
results_dir_name = "results_20240423/"


def upload_to_aws(local_folder, s3_location):
    for root, _, files in os.walk(local_folder):
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


def do_analysis(repo_url, repo_name, save_location, save_on_aws=False):
    repository = pypi_analysis(
        repo_url, repo_name, save_location, results_location=results_dir_name
    )
    if not os.path.exists(save_location):
        try:
            repository.clone_repo()
        except GitCommandError:
            print(f"Git clone error for {repo_name}.")
            if os.path.exists(save_location):
                shutil.rmtree(save_location)
            return

    if save_on_aws:
        upload_to_aws(save_location, "pypi_analysis/data/" + repo_name)

    try:
        repository.analysis()
    except Exception as e:
        print(f"Could not analyse repository {repo_name} due to error:\n {e}")
    else:

        if os.path.exists(os.path.join(results_dir_name, repo_name + ".json")):
            print("Writing results of FawltyDeps analysis to disk.")

            # try:
            #     client.upload_file(
            #         os.path.join(results_dir_name, repo_name + ".json"),
            #         bucket,
            #         os.path.join(
            #             "pypi_analysis", results_dir_name, repo_name + ".json"
            #         ),
            #     )
            # except ClientError as e:
            #     print(f"Client error {e} occurs.")
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
    with ThreadPoolExecutor(max_workers=4) as ex:
        for repo in repositories:
            address = repo["repo_url"].split("github.com/")[1].split("/")
            owner = address[0]
            repo_name = address[1]
            repo_url = f"https://:@github.com/{owner}/{repo_name}.git"
            save_location = "temp/" + repo_name

            result = ex.submit(do_analysis, repo_url, repo_name, save_location)
            result.add_done_callback(lambda _x: pbar.update())
            tasks.append(result)
        wait(tasks)
