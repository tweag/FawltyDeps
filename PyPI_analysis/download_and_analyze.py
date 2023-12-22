import json
import subprocess

from git import Repo


class pypi_analysis:
    def __init__(self, repo_url: str, repo_name: str, save_location: str):
        self.repo_url = repo_url
        self.repo_name = repo_name
        self.save_location = save_location

    def clone_repo(self):
        Repo.clone_from(self.repo_url, self.save_location)

    def analysis(self):
        command = f"cd {self.save_location} && python -m PyPI_analysis --project-name {self.repo_name} --json"
        # Run the command
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, text=True)

        if result.returncode == 0:
            # Parse the JSON output
            try:
                analysis_data = json.loads(result.stdout)

                # Specify the path to the JSON file
                json_file_path = f"results/{self.repo_name}.json"

                # Save the analysis data to the JSON file
                with open(json_file_path, "w") as json_file:
                    json.dump(analysis_data, json_file, indent=2)

            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
        else:
            print(f"Command failed with return code {result.returncode}")
