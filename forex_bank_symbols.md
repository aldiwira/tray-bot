# Forex Pairs & Central Bank Data Reference (Yahoo Finance)

Reference mapping of major interbank currency pairs on Yahoo Finance, categorized by tier, driving Central Banks, pip sizes, and liquidity profiles.

All tickers follow Yahoo's FX convention: `[BASE][QUOTE]=X`.

---

## 1. Major Pairs (Highest Interbank Volume & Tightest Spreads)

Driven by the world's primary reserve central banks.

| Symbol | Yahoo Ticker | Base Currency | Quote Currency | Central Banks (Monetary Policy) | Standard Pip | Typical Active Session |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EURUSD** | `EURUSD=X` | Euro (EUR) | US Dollar (USD) | European Central Bank (ECB) vs Federal Reserve (Fed) | 0.0001 | London / New York |
| **GBPUSD** | `GBPUSD=X` | British Pound (GBP) | US Dollar (USD) | Bank of England (BoE) vs Federal Reserve (Fed) | 0.0001 | London / New York |
| **USDJPY** | `USDJPY=X` | US Dollar (USD) | Japanese Yen (JPY) | Federal Reserve (Fed) vs Bank of Japan (BoJ) | 0.01 | Tokyo / New York |
| **USDCHF** | `USDCHF=X` | US Dollar (USD) | Swiss Franc (CHF) | Federal Reserve (Fed) vs Swiss National Bank (SNB) | 0.0001 | London / New York |
| **AUDUSD** | `AUDUSD=X` | Australian Dollar (AUD) | US Dollar (USD) | Reserve Bank of Australia (RBA) vs Federal Reserve (Fed) | 0.0001 | Sydney / Tokyo / NY |
| **USDCAD** | `USDCAD=X` | US Dollar (USD) | Canadian Dollar (CAD) | Federal Reserve (Fed) vs Bank of Canada (BoC) | 0.0001 | New York |
| **NZDUSD** | `NZDUSD=X` | New Zealand Dollar (NZD) | US Dollar (USD) | Reserve Bank of New Zealand (RBNZ) vs Federal Reserve (Fed) | 0.0001 | Sydney / Tokyo |

---

## 2. Major Cross Pairs (Non-USD Interbank)

High volatility, widely traded across European and Asian banking desks.

| Symbol | Yahoo Ticker | Base Currency | Quote Currency | Central Banks | Standard Pip | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EURGBP** | `EURGBP=X` | Euro (EUR) | British Pound (GBP) | ECB vs BoE | 0.0001 | London interbank flow |
| **EURJPY** | `EURJPY=X` | Euro (EUR) | Japanese Yen (JPY) | ECB vs BoJ | 0.01 | High trend volatility |
| **GBPJPY** | `GBPJPY=X` | British Pound (GBP) | Japanese Yen (JPY) | BoE vs BoJ | 0.01 | "The Beast" / Dragon (wide ATR) |
| **EURCHF** | `EURCHF=X` | Euro (EUR) | Swiss Franc (CHF) | ECB vs SNB | 0.0001 | Safe-haven corridor |
| **AUDJPY** | `AUDJPY=X` | Australian Dollar (AUD) | Japanese Yen (JPY) | RBA vs BoJ | 0.01 | Global risk-on / risk-off gauge |
| **CADJPY** | `CADJPY=X` | Canadian Dollar (CAD) | Japanese Yen (JPY) | BoC vs BoJ | 0.01 | Oil & commodity sensitive |

---

## 3. Emerging & Regional Bank Pairs

| Symbol | Yahoo Ticker | Base Currency | Quote Currency | Central Banks | Standard Pip | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **USDIDR** | `USDIDR=X` | US Dollar (USD) | Indonesian Rupiah (IDR) | Federal Reserve (Fed) vs Bank Indonesia (BI) | 1.00 | High spread, Asian session |
| **USDSGD** | `USDSGD=X` | US Dollar (USD) | Singapore Dollar (SGD) | Federal Reserve (Fed) vs Monetary Authority of Singapore (MAS) | 0.0001 | Major Asian financial hub |
| **USDHKD** | `USDHKD=X` | US Dollar (USD) | Hong Kong Dollar (HKD) | Federal Reserve (Fed) vs Hong Kong Monetary Authority (HKMA) | 0.0001 | Pegged band (7.75 - 7.85) |

---

## 4. Central Bank Reference Key

| Central Bank | Code | Currency | Impact Events to Watch |
| :--- | :--- | :--- | :--- |
| **Federal Reserve (Fed)** | FOMC | USD | Interest Rate Decision, Non-Farm Payrolls (NFP), CPI |
| **European Central Bank** | ECB | EUR | Main Refinancing Rate, Press Conference, Harmonized CPI |
| **Bank of England** | BoE | GBP | Official Bank Rate, MPC Voting, GDP |
| **Bank of Japan** | BoJ | JPY | Policy Rate, Yield Curve Control (YCC), Core CPI |
| **Swiss National Bank** | SNB | CHF | SNB Policy Rate, Quarterly Assessments |
| **Reserve Bank of Australia** | RBA | AUD | Cash Rate Target, Employment Change |
| **Bank of Canada** | BoC | CAD | Overnight Rate Target, CPI, Oil Inventory |
| **Bank Indonesia** | BI | IDR | BI-Rate Decision, Foreign Reserves |

---

## 5. How to add to `config.yaml`

To enable any pair in this trading bot, append to `symbols` in `/home/aldi/experiance/trading-bot/config.yaml`:

```yaml
symbols:
  - symbol: EURUSD
    yahoo: "EURUSD=X"
  - symbol: GBPUSD
    yahoo: "GBPUSD=X"
  - symbol: USDJPY
    yahoo: "USDJPY=X"
  - symbol: USDCHF
    yahoo: "USDCHF=X"
  - symbol: AUDUSD
    yahoo: "AUDUSD=X"
  - symbol: GBPJPY
    yahoo: "GBPJPY=X"
```
