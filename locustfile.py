from locust import HttpUser, task, between

class DjangoUser(HttpUser):
    wait_time = between(1, 3)  # Time between tasks in seconds
    host = "http://127.0.0.1:8000"  # Base URL of your Django application
    access_token = None  # To store the access token
    refresh_token = None  # To store the refresh token

    def on_start(self):
        """
        This method is called when the Locust user starts.
        It ensures login and token retrieval happen before any tasks.
        """
        for attempt in range(3):  # Retry login up to 3 times
            self.login()
            if self.access_token:
                print("Login successful, tokens retrieved.")
                break
            else:
                print(f"Login attempt {attempt + 1} failed.")

        if not self.access_token:
            print("Failed to log in after 3 attempts.")

    def login(self):
        """
        Simulates a POST request to the login endpoint to obtain the authentication tokens.
        """
        response = self.client.post("/api/v1/accounts/login/", json={
            "email_or_phone": "oohychatgpt@gmail.com",
            "password": "Pqr@123",
        })
        print(f"Login response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            # Extract the 'access' and 'refresh' tokens from the response
            self.access_token = response.json().get("data", {}).get("access")
            self.refresh_token = response.json().get("data", {}).get("refresh")
            if self.access_token and self.refresh_token:
                print("Tokens retrieved successfully.")
            else:
                print("Failed to retrieve tokens from login response.")
        else:
            print(f"Login failed: {response.status_code} - {response.text}")

    @task(2)
    def pdf(self):
        """
        Sends a GET request to fetch the PDF.
        If the token is not available, it skips the task.
        """
        if self.access_token:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            params = {
                "report_history_id": "1",
                "service_ids": "7,8,10",
            }
            print(f"Headers: {headers}")
            print(f"Params: {params}")
            response = self.client.get(
                "/api/v1/dynamic-report-service/download-diagnosis-report-buffer/",
                headers=headers,
                params=params
            )
            if response.status_code == 200:
                print(f"PDF request successful: {response.status_code}")
            else:
                print(f"PDF request failed: {response.status_code} - {response.text}")
        else:
            print("No access token available. Skipping PDF task.")

    @task(1)
    def patient_profile(self):
        """
        Sends a GET request to fetch the patient profile.
        If the token is not available, it skips the task.
        """
        if self.access_token:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            response = self.client.get("/api/v1/patient_profile/profile/", headers=headers)
            if response.status_code == 200:
                print(f"Patient profile request successful: {response.status_code}")
            else:
                print(f"Patient profile request failed: {response.status_code} - {response.text}")
        else:
            print("No access token available. Skipping patient profile task.")

    @task(1)
    def logout(self):
        """
        Sends a GET request to log out the user by blacklisting the tokens.
        """
        if self.refresh_token:
            headers = {
                "Authorization": f"Bearer {self.access_token}"  # Include the access token in the Authorization header
            }
            params = {
                "refresh": self.refresh_token  # Pass the refresh token as a query parameter
            }
            response = self.client.get("/api/v1/accounts/logout/", headers=headers, params=params)
            print(f"Logout response: {response.status_code} - {response.text}")
            if response.status_code == 200:  # Successful logout
                print("Logout successful.")
                self.access_token = None
                self.refresh_token = None  # Clear tokens after logout
            else:
                print(f"Logout failed: {response.status_code} - {response.text}")
        else:
            print("No refresh token available for logout.")
