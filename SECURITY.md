# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability within this project, please send an email to nikitashtanko@yahoo.com. All security vulnerabilities will be promptly addressed.

Please do not disclose security vulnerabilities publicly until they have been handled by the maintainers.

## Security Considerations

This application handles:
- API keys and tokens
- Personal data stored in Obsidian vaults
- Telegram message content

### Best Practices

When using this application:

1. Never commit your `.env` file or any files containing sensitive information
2. Regularly rotate API keys and tokens
3. Store your Obsidian vault in a secure location
4. Review third-party dependencies regularly for vulnerabilities
5. Keep your Docker containers and host systems updated

## Dependency Security

The project uses several dependencies. Please ensure you keep them updated:

```bash
pip install --upgrade -r requirements.txt
```

You can check for vulnerabilities in your dependencies using tools like `safety`:

```bash
pip install safety
safety check -r requirements.txt
``` 