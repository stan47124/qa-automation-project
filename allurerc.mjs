// Compatible with Allure Report 3.16.0. No external JS dependencies required.
// Only a disposable transaction file is passed here, never committed history.
export default {
  name: "QA Automation Project",
  ...(process.env.ALLURE_HISTORY_PATH
    ? { historyPath: process.env.ALLURE_HISTORY_PATH, appendHistory: true, historyLimit: 20 }
    : { appendHistory: false }),
  plugins: {
    awesome: {
      options: {
        reportName: "QA Automation Project",
        groupBy: ["feature", "story"],
        charts: [
          { type: "currentStatus", title: "Current status" },
          { type: "testResultSeverities", title: "Test results by severity", includeUnset: true },
          { type: "successRateDistribution", title: "Success rate distribution" },
          { type: "coverageDiff", title: "Coverage diff map" },
          { type: "durations", title: "Durations histogram", groupBy: "none" },
          { type: "statusDynamics", title: "Status dynamics", limit: 20 },
          { type: "statusTransitions", title: "Status transitions", limit: 20 },
          { type: "testBaseGrowthDynamics", title: "Test base growth", limit: 20 },
          { type: "stabilityDistribution", title: "Stability by feature",
            groupBy: "feature", threshold: 90, limit: 10, stabilizationPeriod: 5,
            skipStatuses: ["skipped", "unknown"] },
        ],
      },
    },
  },
};
