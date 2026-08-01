/* version.js
 * Zentrale Versionsangabe für alle Seiten des Repos. Bindet sich selbst als
 * schmalen Footer unten auf jede Seite ein, die dieses Script lädt - bei
 * einem Update also nur HIER die Version/Datum anpassen, nicht auf jeder
 * einzelnen Seite.
 */
(function () {
  const APP_VERSION = "v2";
  const APP_VERSION_DATE = "01.08.2026 07:58";

  const footer = document.createElement("div");
  footer.id = "appVersionFooter";
  footer.style.cssText =
    "text-align:center;font-family:'IBM Plex Mono',monospace;font-size:10px;" +
    "color:#9AA1AC;margin-top:40px;padding:16px 0 0;border-top:1px solid #E3E6EA;" +
    "max-width:1080px;width:100%;align-self:center;";
  footer.textContent = `${APP_VERSION} vom ${APP_VERSION_DATE}`;
  document.body.appendChild(footer);
})();
