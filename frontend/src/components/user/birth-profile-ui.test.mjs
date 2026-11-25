import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(__dirname, "../..");

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      const mapped = path.join(SRC_ROOT, specifier.slice(2));
      for (const ext of ["", ".ts", ".tsx", ".json"]) {
        const candidate = `${mapped}${ext}`;
        try {
          readFileSync(candidate);
          return nextResolve(pathToFileURL(candidate).href, context);
        } catch {
          // Try next extension
        }
      }
    }
    if (specifier.startsWith(".") && context.parentURL?.startsWith("file:")) {
      const parentDir = path.dirname(fileURLToPath(context.parentURL));
      const base = path.resolve(parentDir, specifier);
      for (const ext of ["", ".ts", ".tsx", ".json"]) {
        const candidate = `${base}${ext}`;
        try {
          readFileSync(candidate);
          return nextResolve(pathToFileURL(candidate).href, context);
        } catch {
          // Try next extension
        }
      }
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.startsWith("file:") && (url.endsWith(".tsx") || url.endsWith(".ts"))) {
      const source = readFileSync(fileURLToPath(url), "utf8");
      const transpiled = ts.transpileModule(source, {
        fileName: fileURLToPath(url),
        compilerOptions: {
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2022,
          jsx: ts.JsxEmit.ReactJSX,
          esModuleInterop: true,
        },
      });
      return {
        format: "module",
        shortCircuit: true,
        source: transpiled.outputText,
      };
    }
    return nextLoad(url, context);
  },
});

const React = await import("react");
const { renderToStaticMarkup } = await import("react-dom/server");
const enMessages = JSON.parse(readFileSync(path.join(SRC_ROOT, "i18n/en.json"), "utf8"));
const neMessages = JSON.parse(readFileSync(path.join(SRC_ROOT, "i18n/ne.json"), "utf8"));
const { BirthProfileForm } = await import("./BirthProfileForm.tsx");
const { UserChartWorkspace } = await import("./UserChartWorkspace.tsx");

const t = enMessages.userWorkspace;

const formLabels = {
  formTitle: t.formTitle,
  editFormTitle: t.editFormTitle,
  formSubtitle: t.formSubtitle,
  authFormLockedNotice: t.authFormLockedNotice,
  formLabel: t.formLabel,
  formLabelPlaceholder: t.formLabelPlaceholder,
  formInputCalendar: t.formInputCalendar,
  formDate: t.formDate,
  formCertainty: t.formCertainty,
  formTime: t.formTime,
  formTimeUnknownNote: t.formTimeUnknownNote,
  formPlace: t.formPlace,
  formPlacePlaceholder: t.formPlacePlaceholder,
  formTimezone: t.formTimezone,
  formTimezonePlaceholder: t.formTimezonePlaceholder,
  formLatitude: t.formLatitude,
  formLongitude: t.formLongitude,
  formLatitudePlaceholder: t.formLatitudePlaceholder,
  formLongitudePlaceholder: t.formLongitudePlaceholder,
  formCoordinatesNote: t.formCoordinatesNote,
  formSubmit: t.formSubmit,
  editFormSubmit: t.editFormSubmit,
  formSaving: t.formSaving,
  formCancel: t.formCancel,
  loadSampleButton: t.loadSampleButton,
  timeExact: t.timeExact,
  timeApproximate: t.timeApproximate,
  timeUnknown: t.timeUnknown,
};

describe("BirthProfileForm and UserChartWorkspace rendered UI states", () => {
  it("renders unauthenticated state cleanly with disabled save and no prefilled Kathmandu values", () => {
    const html = renderToStaticMarkup(
      React.createElement(UserChartWorkspace, {
        messagesByLocale: { en: enMessages.userWorkspace, ne: neMessages.userWorkspace },
      })
    );

    assert.match(html, /Authentication Required to Manage Saved Profiles/);
    assert.match(html, /Preview Synthetic Sample \(London, 2015\)/);
    assert.match(html, /type="submit" disabled=""[^>]*>Save Profile/);
    assert.equal(html.includes('value="Kathmandu, Nepal"'), false);
    assert.equal(html.includes('value="27.7172"'), false);
    assert.equal(html.includes('value="85.3240"'), false);
    assert.equal(html.includes('value="2055-04-15"'), false);
  });

  it("renders authenticated create mode with blank explicit fields and server error alerts", () => {
    const html = renderToStaticMarkup(
      React.createElement(BirthProfileForm, {
        mode: "create",
        canCancel: true,
        isAuthenticated: true,
        serverErrors: ["Timezone must be a valid region-based IANA identifier or UTC"],
        onSubmitProfile: () => {},
        onLoadSyntheticSample: () => {},
        onCancel: () => {},
        labels: formLabels,
      })
    );

    assert.match(html, />Create Birth Profile</);
    assert.match(html, /type="submit"[^>]*>Save Profile</);
    assert.equal(html.includes('type="submit" disabled=""'), false);
    assert.match(html, /role="alert"[^>]*>.*Timezone must be a valid region-based IANA identifier or UTC/);
  });

  it("renders edit mode prefilled cleanly from saved BS unknown-time profile", () => {
    const html = renderToStaticMarkup(
      React.createElement(BirthProfileForm, {
        mode: "edit",
        canCancel: true,
        isAuthenticated: true,
        initialProfile: {
          id: "prof-edit-1",
          label: "Ramesh Pokhara",
          input_calendar: "BS",
          entered_date: "2055-04-15",
          date_ad: null,
          bs_conversion_status: "awaiting_bs_conversion",
          time_certainty: "unknown",
          time_local: null,
          place_name: "Pokhara, Nepal",
          latitude: 28.2096,
          longitude: 83.9856,
          timezone: "Asia/Kathmandu",
          is_synthetic_sample: false,
        },
        onSubmitProfile: () => {},
        onLoadSyntheticSample: () => {},
        onCancel: () => {},
        labels: formLabels,
      })
    );

    assert.match(html, />Edit Birth Profile</);
    assert.match(html, />Update Profile</);
    assert.match(html, /value="Ramesh Pokhara"/);
    assert.match(html, /value="2055-04-15"/);
    assert.match(html, /value="Pokhara, Nepal"/);
    assert.match(html, /value="28\.2096"/);
    assert.match(html, /value="83\.9856"/);
    assert.match(html, /id="bp-time"[^>]*disabled=""/);
  });
});
