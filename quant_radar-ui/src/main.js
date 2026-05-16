import { jsx as _jsx } from "react/jsx-runtime";
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { queryClient } from "./lib/query";
import "./styles/globals.css";
const root = createRoot(document.getElementById("root"));
root.render(_jsx(StrictMode, { children: _jsx(QueryClientProvider, { client: queryClient, children: _jsx(App, {}) }) }));
