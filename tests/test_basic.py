import unittest
import os

class TestEnvironment(unittest.TestCase):
    """Basic tests to verify the environment is set up correctly."""
    
    def test_environment_variables(self):
        """Test that environment variables can be loaded."""
        # This is just a placeholder test to verify pytest works
        self.assertTrue(os.path.exists('.env') or 'GEMINI_API_KEY' in os.environ, 
                        "Environment file or variables should be available")
    
    def test_requirements(self):
        """Test that requirements file exists."""
        self.assertTrue(os.path.exists('requirements.txt'), 
                        "Requirements file should exist")

if __name__ == '__main__':
    unittest.main() 