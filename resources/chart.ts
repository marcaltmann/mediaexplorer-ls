import { axisBottom } from "d3-axis";
import { json } from "d3-fetch";
import { NumberValue, scaleLinear } from "d3-scale";
import { select, pointer } from "d3-selection";
import type { Chapter } from "./types";

document.addEventListener("DOMContentLoaded", buildChart);

async function buildChart() {
  const mediaElement = document.getElementById(
    "media-element",
  ) as HTMLMediaElement;

  // This should be handled with an assertion, not with a silent default.
  const resourceId = Number.parseInt(mediaElement.dataset.id || "0");
  const duration = Number.parseFloat(mediaElement.dataset.duration || "0");

  const chapters: Array<Chapter> | undefined = await json(
    `/resources/${resourceId}/toc`,
  );
  const waveform: Array<number> | undefined = await json(
    `/resources/${resourceId}/waveform`,
  );

  document.addEventListener("keydown", (e) => {
    if (
      [
        "Digit1",
        "Digit2",
        "Digit3",
        "Digit4",
        "Digit5",
        "Digit6",
        "Digit7",
        "Digit8",
        "Digit9",
        "Digit0",
      ].includes(e.code)
    ) {
      e.preventDefault();

      const digit = Number.parseInt(e.code[5]);
      const chapterNum = digit === 0 ? 10 : digit;

      if (chapters && chapters.length >= chapterNum) {
        const time = chapters[chapterNum - 1].position;
        mediaElement.currentTime = time;
        mediaElement.play();
      }
    }
  });

  // Declare the chart dimensions and margins.
  const width = 1320;
  const height = 200;
  const marginTop = 20;
  const marginRight = 0;
  const marginBottom = 30;
  const marginLeft = 0;

  // Declare the x (horizontal position) scale.
  const xScale = scaleLinear()
    .domain([0, duration])
    .range([marginLeft, width - marginRight]);

  const xAxis = axisBottom(xScale).tickFormat((d: any) => {
    const hours = Math.floor(d / 3600);
    const minutes = Math.floor((d % 3600) / 60);
    const seconds = Math.floor(d % 60);

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    } else {
      return `${minutes}:${seconds.toString().padStart(2, "0")}`;
    }
  });

  const svg = select("#container")
    .append("svg")
    .attr("width", width)
    .attr("height", height);

  svg
    .append("rect")
    .attr("id", "progress")
    .attr("x", xScale(0))
    .attr("y", 0)
    .attr("width", xScale(mediaElement?.currentTime) - xScale(0))
    .attr("height", height)
    .attr("fill", "var(--accent-color)")
    .attr("opacity", 0.5);

  svg
    .append("g")
    .attr("transform", `translate(0,${height - marginBottom})`)
    .call(xAxis);

  /* Waveform */
  if (waveform) {
    svg
      .selectAll(".waveform-line")
      .data(waveform)
      .join("line")
      .classed("waveform-line", true)
      .attr("x1", (d: number, idx: number) => xScale(idx / 10))
      .attr("x2", (d: number, idx: number) => xScale(idx / 10))
      .attr("y1", (d: number) => (height - marginBottom) / 2 - d)
      .attr("y2", (d: number) => (height - marginBottom) / 2 + d)
      .attr("stroke", "gray");
  }

  /* TOC */
  if (chapters) {
    svg
      .selectAll(".chapter-line")
      .data(chapters)
      .join("line")
      .classed("chapter-line", true)
      .attr("x1", (d: Chapter) => xScale(d.position))
      .attr("x2", (d: Chapter) => xScale(d.position))
      .attr("y1", 0)
      .attr("y2", height - marginBottom)
      .attr("stroke", "var(--secondary-color)");

    svg
      .selectAll(".chapter-name")
      .data(chapters)
      .join("text")
      .classed("chapter-name", true)
      .attr("x", (d: Chapter) => xScale(d.position) + 10)
      .attr("y", 5)
      .attr("fill", "var(--secondary-color)")
      .attr("font-size", "12px")
      .text((d: Chapter) => d.name);
  }

  /* Invisible click area */
  svg
    .append("rect")
    .attr("width", width)
    .attr("height", height)
    .attr("fill", "transparent")
    .style("cursor", "crosshair")
    .on("click", (event: Event) => {
      const [mouseX] = pointer(event);
      const seconds = xScale.invert(mouseX);
      mediaElement.currentTime = seconds;
      mediaElement.play();
    });

  mediaElement.addEventListener("timeupdate", (event: Event) => {
    select("#progress").attr(
      "width",
      xScale(mediaElement.currentTime) - xScale(0),
    );
  });
}
