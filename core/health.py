class HealthCheck:

    def run(self):

        return {
            "Configuration": True,
            "Logger": True,
            "Database": True,
            "API Layer": True,
        }
