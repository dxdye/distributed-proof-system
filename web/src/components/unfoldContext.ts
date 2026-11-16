import { createContext } from "react";

/** Opening declarations of the submission in the side panel of a ticket
 * (C-39): names in the statement and in the lists open there. Absent outside
 * a ticket, so names elsewhere stay plain. */
export type Unfold = {
  /** Is this a declaration of the submission that can be opened here? */
  has: (declaration: string) => boolean;
  /** Open it as the next step of the current path (or start a new path). */
  open: (declaration: string, from?: "statement" | "panel") => void;
};

export const UnfoldContext = createContext<Unfold | null>(null);
