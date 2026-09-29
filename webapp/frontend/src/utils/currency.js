// Mirrors webapp/backend/rates.py SUPPORTED_CURRENCIES.
export const SUPPORTED_CURRENCIES = [
  "USD",
  "EUR",
  "GBP",
  "JPY",
  "AUD",
  "CAD",
  "CHF",
  "CNY",
  "INR",
  "AED",
  "SAR",
  "EGP",
];

const SYMBOLS = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CNY: "¥",
  INR: "₹",
};

export function formatMoney(amount, currency) {
  const symbol = SYMBOLS[currency];
  const value = amount.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  return symbol ? `${symbol}${value}` : `${value} ${currency}`;
}
