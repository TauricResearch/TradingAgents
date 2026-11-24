// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** The terminal's theme for every view, decided once at startup (plain unless the app sets one). */
import { createContext, useContext } from "react";
import { plainTheme, type Roles, rolesOf, type Theme } from "./theme.js";

export const ThemeContext = createContext<Theme>(plainTheme);

export function useTheme(): Theme {
  return useContext(ThemeContext);
}

/** The theme's roles: what components style text by (see theme.ts). */
export function useRoles(): Roles {
  return rolesOf(useContext(ThemeContext));
}
