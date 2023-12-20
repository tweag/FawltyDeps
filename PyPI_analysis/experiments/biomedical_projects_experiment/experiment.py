import json
import os
import boto3
import shutil

from PyPI_analysis.download_and_analyze import pypi_analysis

json_file_path = "repositories.json"
client = boto3.client('s3')
bucket = "fawltydeps-tweag"


def upload_to_aws(local_folder, s3_location):
    for root, dirs, files in os.walk(local_folder):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_folder)
            s3_path = os.path.join(s3_location, relative_path)
            client.upload_file(local_path, bucket, s3_path)

with open(json_file_path, "r") as file:
    repositories = json.load(file)

for repo in repositories:
    repo_url = "https://" + repo["domain"] + "/" + repo["repository"] + ".git"
    repo_name = repo["repository"].split("/")[-1]
    save_location = "temp/" + repo_name

    repository = pypi_analysis(repo_url, repo_name, save_location)

    if not os.path.exists(save_location):
        repository.clone_repo()

    upload_to_aws(save_location, "pypi_analysis/data/"+repo_name)
    
    repository.analysis()

    upload_to_aws("results/", "pypi_analysis/results/")

    shutil.rmtree(save_location)
