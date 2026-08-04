import { mkdir, writeFile } from "node:fs/promises";

const token = process.env.GITHUB_TOKEN;
const login = process.env.PROFILE_USER;

if (!token || !login) {
  throw new Error("GITHUB_TOKEN and PROFILE_USER are required.");
}

const to = new Date();
const from = new Date(to);
from.setUTCDate(from.getUTCDate() - 364);

const query = `
  query ($login: String!, $from: DateTime!, $to: DateTime!) {
    user(login: $login) {
      contributionsCollection(from: $from, to: $to) {
        contributionCalendar {
          totalContributions
          weeks {
            firstDay
            contributionDays {
              contributionCount
            }
          }
        }
      }
    }
  }
`;

const response = await fetch("https://api.github.com/graphql", {
  method: "POST",
  headers: {
    authorization: `Bearer ${token}`,
    "content-type": "application/json",
    "user-agent": "Dev0910-profile-metrics",
  },
  body: JSON.stringify({
    query,
    variables: {
      login,
      from: from.toISOString(),
      to: to.toISOString(),
    },
  }),
});

if (!response.ok) {
  throw new Error(`GitHub GraphQL request failed with ${response.status}.`);
}

const payload = await response.json();
if (payload.errors?.length) {
  throw new Error(payload.errors.map((error) => error.message).join("; "));
}

const calendar = payload.data?.user?.contributionsCollection?.contributionCalendar;
if (!calendar?.weeks?.length) {
  throw new Error(`No contribution calendar returned for ${login}.`);
}

const weeks = calendar.weeks.slice(-52).map((week) => ({
  date: week.firstDay,
  total: week.contributionDays.reduce((sum, day) => sum + day.contributionCount, 0),
}));

const width = 900;
const height = 260;
const left = 50;
const right = 874;
const top = 68;
const bottom = 218;
const chartWidth = right - left;
const chartHeight = bottom - top;
const highest = Math.max(1, ...weeks.map((week) => week.total));
const ceiling = Math.max(4, Math.ceil(highest / 4) * 4);

const x = (index) => left + (chartWidth * index) / Math.max(1, weeks.length - 1);
const y = (value) => bottom - (chartHeight * value) / ceiling;
const pointPath = weeks.map((week, index) => `${x(index).toFixed(1)},${y(week.total).toFixed(1)}`).join(" ");
const areaPath = `M ${left} ${bottom} L ${pointPath.replaceAll(" ", " L ")} L ${right} ${bottom} Z`;

const horizontalGrid = [0, 0.25, 0.5, 0.75, 1]
  .map((ratio) => {
    const gridY = bottom - chartHeight * ratio;
    const label = Math.round(ceiling * ratio);
    return `<line class="grid" x1="${left}" y1="${gridY}" x2="${right}" y2="${gridY}"/><text class="axis" x="${left - 10}" y="${gridY + 4}" text-anchor="end">${label}</text>`;
  })
  .join("");

const monthLabels = [0, 13, 26, 39, 51]
  .filter((index) => weeks[index])
  .map((index) => {
    const label = new Intl.DateTimeFormat("en", { month: "short", year: "2-digit", timeZone: "UTC" }).format(new Date(`${weeks[index].date}T00:00:00Z`));
    return `<text class="axis" x="${x(index)}" y="244" text-anchor="middle">${label}</text>`;
  })
  .join("");

const recentPoints = weeks
  .map((week, index) => ({ week, index }))
  .slice(-8)
  .map(({ week, index }) => `<circle cx="${x(index).toFixed(1)}" cy="${y(week.total).toFixed(1)}" r="2.6" fill="#a78bfa"/>`)
  .join("");

const escapedLogin = login.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title description">
  <title id="title">${escapedLogin} GitHub contribution activity</title>
  <desc id="description">Weekly contribution totals across the most recent 52 weeks. ${calendar.totalContributions} total contributions in the selected period.</desc>
  <defs>
    <linearGradient id="activity-fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.38"/>
      <stop offset="100%" stop-color="#a78bfa" stop-opacity="0.02"/>
    </linearGradient>
    <linearGradient id="activity-line" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#22d3ee"/>
      <stop offset="100%" stop-color="#a78bfa"/>
    </linearGradient>
    <style>
      .title { fill: #22d3ee; font: 600 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      .subtitle, .axis { fill: #8b949e; font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      .grid { stroke: #30363d; stroke-width: 1; opacity: 0.72; }
      @media (prefers-color-scheme: light) {
        .subtitle, .axis { fill: #57606a; }
        .grid { stroke: #d0d7de; }
      }
    </style>
  </defs>
  <text class="title" x="${left}" y="26">Contribution Activity</text>
  <text class="subtitle" x="${left}" y="47">${calendar.totalContributions} contributions · weekly totals · last 52 weeks</text>
  ${horizontalGrid}
  <path d="${areaPath}" fill="url(#activity-fill)"/>
  <polyline points="${pointPath}" fill="none" stroke="url(#activity-line)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  ${recentPoints}
  ${monthLabels}
</svg>
`;

await mkdir("assets/metrics", { recursive: true });
await writeFile("assets/metrics/activity-graph.svg", svg, "utf8");
console.log(`Generated activity graph for ${login}: ${calendar.totalContributions} contributions.`);
