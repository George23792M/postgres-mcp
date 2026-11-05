"""Run the authenticated Postgres MCP server."""

import sys
from app.server import create_server


def main():
    try:
        """Start the server with the streamable HTTP transport."""
        create_server().run(transport="streamable-http")
    except KeyboardInterrupt:
        print(f"Sever shutdown gracefully")
        sys.exit(0)


if __name__ == "__main__":
    main()
