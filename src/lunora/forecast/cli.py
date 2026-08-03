import asyncio
import sys


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "all"

    async def run():
        if action in ("generate", "all"):
            from lunora.forecast.generate import generate_daily_forecasts
            await generate_daily_forecasts()
        if action in ("send", "all"):
            from lunora.forecast.send import send_daily_forecasts
            await send_daily_forecasts()

    asyncio.run(run())


if __name__ == "__main__":
    main()
