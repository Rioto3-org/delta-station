function helloWorld() {
  Logger.log("Hello, world!");
  SpreadsheetApp.getActiveSpreadsheet().getSheets()[0].appendRow([new Date(), "Hello, world!"]);
}
