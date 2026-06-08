/** Booker phone: optional leading +, then digits only. */

export function sanitizePhoneInput(value: string): string {
  let out = "";
  for (const char of value) {
    if (char >= "0" && char <= "9") {
      out += char;
    } else if (char === "+" && out.length === 0) {
      out += char;
    }
  }
  return out;
}

export function isValidBookerPhone(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) {
    return true;
  }
  return /^\+[0-9]{6,15}$/.test(trimmed);
}
