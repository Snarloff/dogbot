import asyncio


async def shell(cmd: str) -> str:
    """
    Executes a shell command asynchronously.
    Args:
        cmd: The command to execute.

    Returns: The command output.
    """
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    results = await process.communicate()
    return ''.join(x.decode('utf-8') for x in results)
