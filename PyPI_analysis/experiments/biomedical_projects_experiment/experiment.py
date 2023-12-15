import json
import os

from PyPI_analysis.download_and_analyze import pypi_analysis

json_file_path = "repositories.json"

with open(json_file_path, "r") as file:
    repositories = json.load(file)

for repo in repositories:
    repo_url = "https://" + repo["domain"] + "/" + repo["repository"] + ".git"
    repo_name = repo["repository"].split("/")[-1]
    save_location = "temp/" + repo_name

    repository = pypi_analysis(repo_url, repo_name, save_location)

    if not os.path.exists(save_location):
        repository.clone_repo()

    repository.analysis()
