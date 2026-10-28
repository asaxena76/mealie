/* tslint:disable */

/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export interface CarrieAccepted {
  runId: string;
}
export interface CarrieContext {
  startDate: string;
  endDate: string;
  dinerIds?: string[];
  includeCooking?: boolean;
}
export interface CarrieHistory {
  messages: CarrieMessage[];
  running?: boolean;
  leafEntryId?: string | null;
  truncated?: boolean;
}
export interface CarrieMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}
export interface CarrieSend {
  startDate: string;
  endDate: string;
  dinerIds?: string[];
  includeCooking?: boolean;
  message: string;
  requestId: string;
  expectedLeafEntryId?: string | null;
}
export interface CarrieStatus {
  enabled: boolean;
  stockPath?: string | null;
  stockAgentId?: string | null;
}
