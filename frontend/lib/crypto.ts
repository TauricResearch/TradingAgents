/**
 * Crypto utilities for secure API key storage
 * Uses AES-256-GCM encryption with Web Crypto API
 */

// Storage keys
const SALT_KEY = "tradingagents_crypto_salt";
const IV_PREFIX = "tradingagents_iv_";

/**
 * Generate a random salt for key derivation
 */
function generateSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(16));
}

/**
 * Get or create the salt stored in localStorage
 */
function getOrCreateSalt(): Uint8Array {
  if (typeof window === "undefined") {
    return new Uint8Array(16);
  }

  const storedSalt = localStorage.getItem(SALT_KEY);
  if (storedSalt) {
    return Uint8Array.from(atob(storedSalt), (c) => c.charCodeAt(0));
  }

  const newSalt = generateSalt();
  localStorage.setItem(SALT_KEY, btoa(String.fromCharCode(...newSalt)));
  return newSalt;
}

/**
 * Generate a browser fingerprint for key derivation
 * This creates a semi-unique identifier based on browser characteristics
 */
function getBrowserFingerprint(): string {
  if (typeof window === "undefined") {
    return "server-side";
  }

  const components = [
    navigator.userAgent,
    navigator.language,
    screen.width.toString(),
    screen.height.toString(),
    screen.colorDepth.toString(),
    new Date().getTimezoneOffset().toString(),
    navigator.hardwareConcurrency?.toString() || "unknown",
  ];

  return components.join("|");
}

/**
 * Derive an encryption key from the browser fingerprint using PBKDF2
 */
async function deriveKey(salt: Uint8Array): Promise<CryptoKey> {
  const fingerprint = getBrowserFingerprint();
  const encoder = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    encoder.encode(fingerprint),
    "PBKDF2",
    false,
    ["deriveBits", "deriveKey"]
  );

  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: salt.buffer as ArrayBuffer,  // Cast to ArrayBuffer to fix TypeScript error
      iterations: 100000,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}

/**
 * Encrypt a string using AES-256-GCM
 */
export async function encrypt(plaintext: string): Promise<string> {
  if (typeof window === "undefined" || !plaintext) {
    return plaintext;
  }

  try {
    const salt = getOrCreateSalt();
    const key = await deriveKey(salt);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encoder = new TextEncoder();

    const encrypted = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      encoder.encode(plaintext)
    );

    // Combine IV + encrypted data and encode as base64
    const combined = new Uint8Array(iv.length + encrypted.byteLength);
    combined.set(iv);
    combined.set(new Uint8Array(encrypted), iv.length);

    return btoa(String.fromCharCode(...combined));
  } catch (error) {
    console.error("Encryption failed:", error);
    throw new Error("Failed to encrypt data");
  }
}

/**
 * Decrypt a string using AES-256-GCM
 */
export async function decrypt(ciphertext: string): Promise<string> {
  if (typeof window === "undefined" || !ciphertext) {
    return ciphertext;
  }

  try {
    const salt = getOrCreateSalt();
    const key = await deriveKey(salt);

    // Decode from base64
    const combined = Uint8Array.from(atob(ciphertext), (c) => c.charCodeAt(0));

    // Extract IV (first 12 bytes) and encrypted data
    const iv = combined.slice(0, 12);
    const encrypted = combined.slice(12);

    const decrypted = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv },
      key,
      encrypted
    );

    const decoder = new TextDecoder();
    return decoder.decode(decrypted);
  } catch (error) {
    console.error("Decryption failed:", error);
    throw new Error("Failed to decrypt data");
  }
}

/**
 * Check if a string appears to be encrypted (base64 with proper length)
 */
export function isEncrypted(value: string): boolean {
  if (!value || value.length < 20) return false;
  
  try {
    // Try to decode as base64
    const decoded = atob(value);
    // Encrypted data should be at least 12 (IV) + 16 (min ciphertext) bytes
    return decoded.length >= 28;
  } catch {
    return false;
  }
}

/**
 * Encrypt an object (for API settings)
 */
export async function encryptObject(obj: Record<string, string>): Promise<Record<string, string>> {
  const encrypted: Record<string, string> = {};
  
  for (const [key, value] of Object.entries(obj)) {
    if (value && typeof value === "string" && value.trim() !== "") {
      // Only encrypt non-empty values that look like API keys
      if (key.includes("api_key") || key.includes("api_secret")) {
        encrypted[key] = await encrypt(value);
      } else {
        encrypted[key] = value;
      }
    } else {
      encrypted[key] = value;
    }
  }
  
  return encrypted;
}

/**
 * Decrypt an object (for API settings)
 */
export async function decryptObject(obj: Record<string, string>): Promise<Record<string, string>> {
  const decrypted: Record<string, string> = {};
  
  for (const [key, value] of Object.entries(obj)) {
    if (value && typeof value === "string" && isEncrypted(value)) {
      try {
        decrypted[key] = await decrypt(value);
      } catch {
        // If decryption fails, the data might be corrupted or from a different device
        decrypted[key] = "";
      }
    } else {
      decrypted[key] = value;
    }
  }
  
  return decrypted;
}

/**
 * Clear all crypto-related data (useful for logout/reset)
 */
export function clearCryptoData(): void {
  if (typeof window === "undefined") return;
  
  localStorage.removeItem(SALT_KEY);
}
