import unittest
from unittest.mock import patch

from app.database import Database


class DatabaseResilienceTest(unittest.TestCase):
    def test_postgres_pool_checks_connections_before_reuse(self):
        with patch("app.database.ConnectionPool") as pool_class:
            Database("postgresql://user:password@example.test/database")

        options = pool_class.call_args.kwargs
        self.assertIs(options["check"], pool_class.check_connection)
        self.assertEqual(options["min_size"], 0)
        self.assertEqual(options["max_idle"], 60.0)
        self.assertEqual(options["max_lifetime"], 300.0)
        self.assertEqual(options["reconnect_timeout"], 15.0)


if __name__ == "__main__":
    unittest.main()
