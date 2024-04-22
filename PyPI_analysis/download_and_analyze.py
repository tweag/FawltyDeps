import datetime
import json
import subprocess

from git import Repo


class pypi_analysis:
    def __init__(
        self,
        repo_url: str,
        repo_name: str,
        save_location: str,
        results_location: str = "results",
    ):
        self.repo_url = repo_url
        self.repo_name = repo_name
        self.save_location = save_location
        self.json_file_path = f"{results_location}/{self.repo_name}.json"

    def clone_repo(self):
        #     --depth <depth>
        # Create a shallow clone with a history truncated to the specified number of commits.
        # We do not need commit history for the analysis
        Repo.clone_from(self.repo_url, self.save_location, depth=1)

    def analysis(self):
        command = f"cd {self.save_location} && python -m PyPI_analysis --project-name {self.repo_name} --json"
        # Run the command
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, text=True)

        if result.returncode == 0:
            # Parse the JSON output
            try:
                analysis_data = json.loads(result.stdout)
                analysis_data["metadata"]["repo_url"] = self.repo_url
                analysis_data["metadata"][
                    "creation_timestamp"
                ] = datetime.datetime.now().isoformat()

                # Save the analysis data to the JSON file
                with open(self.json_file_path, "w") as json_file:
                    json.dump(analysis_data, json_file, indent=2)

            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
        else:
            print(f"Command failed with return code {result.returncode}")
