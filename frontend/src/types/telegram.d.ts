interface TelegramWebApp {
  ready(): void
  expand(): void
  initData: string
  initDataUnsafe: {
    user?: {
      id: number
      first_name: string
    }
  }
}

interface Window {
  Telegram?: {
    WebApp?: TelegramWebApp
  }
}
