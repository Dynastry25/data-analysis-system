/**
 * Upload formats — the one list the browser is told about, so no surface can
 * fall behind the backend again.
 *
 * This mirrors ALLOWED_EXTENSIONS in backend/app/config.py, and the backend stays
 * authoritative: it re-checks the extension on upload and refuses anything else
 * with a 400. What lives here only decides which files the picker offers and what
 * the helper text promises.
 */

// Delimited and spreadsheet files the backend reads with pandas directly.
export const TABLE_FILE_EXTENSIONS: string[] = [
  ".csv",
  ".xlsx",
  ".json",
  ".tsv",
  ".txt",
  ".parquet",
];

// Statistical package exports, read by the backend through pyreadstat (Stata,
// SPSS) and pyreadr (R). Value labels attached to categorical variables stay
// their numeric codes, so those columns remain usable for statistics.
export const STAT_FILE_EXTENSIONS: string[] = [
  ".dta", // Stata
  ".sav",
  ".zsav",
  ".por", // SPSS
  ".rdata",
  ".rda",
  ".rds", // R
];

export const UPLOAD_FILE_EXTENSIONS: string[] = [
  ...TABLE_FILE_EXTENSIONS,
  ...STAT_FILE_EXTENSIONS,
];

/** The value of an &lt;input type="file"&gt; accept attribute. */
export const UPLOAD_FILE_INPUT_ACCEPT: string = UPLOAD_FILE_EXTENSIONS.join(",");

/** The accepted families named as people know them, in the order they are read. */
export const UPLOAD_FILE_GROUPS =
  "CSV, Excel, JSON, TSV, TXT, Parquet, Stata, SPSS, R";

/** The extensions themselves, for the message shown when a name is rejected. */
export const UPLOAD_FILE_EXTENSION_LIST: string = UPLOAD_FILE_EXTENSIONS.join(
  ", "
);

/** True when a file name ends in one of the accepted extensions. */
export function isAcceptedUploadName(name: string): boolean {
  const lower = name.toLowerCase();
  return UPLOAD_FILE_EXTENSIONS.some((extension) => lower.endsWith(extension));
}
