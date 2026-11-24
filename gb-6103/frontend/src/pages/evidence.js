import { api } from "../api/workbench.js";
import { errorText, field } from "../components/common/fields.js";
import { empty, pageHeading, section } from "../components/common/panel.js";
import { resultTable, table } from "../components/common/table.js";
import { submit } from "../hooks/submit.js";
import { el } from "../utils/dom.js";
import { cell, download, time } from "../utils/format.js";

function reviewForm(id, saved) {
  const form = el("form", {id: "review-form"},
    field("复核意见", el("textarea", {name: "note", required: true, minlength: 3, maxlength: 500, rows: 3})),
    errorText(), el("button", {type: "submit"}, "签署复核"));
  submit(form, async values => saved(await api.submitReview(id, {note: values.get("note")})));
  return form;
}

function signature(review) {
  return el("div", {"data-testid": "reviewed", class: "signature"},
    el("strong", {}, `已签署 · ${review.actor}`), el("p", {}, review.note), el("time", {}, time(review.created_at)));
}

function handoverTable(handovers) {
  return table(["旧站", "新站", "新站枪口", "交接", "说明"],
    handovers.map(item => [item["旧站"], item["新站"], item["新站枪口"], item["交接"], item["说明"]]),
    "交接生效情况");
}

function inServiceTable(roster) {
  return table(["站号", "片区", "枪口", "入册批次"],
    roster.map(item => [item["站号"], item["片区"], item["枪口"], item["批次"]]),
    "在役名册");
}

function holds(rows) {
  return rows.filter(row => row["决定"] === "搁置");
}

export async function evidencePage(config, user, route) {
  const runs = (await api.runs()).filter(item => item.status === "done");
  const run = route.id ? await api.run(route.id) : runs[0];
  if (!run?.result) return el("div", {class: "page"},
    pageHeading(config.modules[3], null), empty("成功执行一个批次后可以查看、签核和下载证据。"),
    el("a", {href: "#runs"}, config.modules[2]));

  const review = await api.review(run.id);
  const issue = errorText();
  const button = el("button", {type: "button", onclick: async () => {
    button.disabled = true;
    issue.textContent = "";
    try {
      await download(await api.export(run.id), `evidence-${run.id}.json`);
    } catch (error) {
      issue.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }}, "导出证据");
  const signing = el("div", {});
  signing.append(review ? signature(review) : user.role === "reviewer" ?
    reviewForm(run.id, data => signing.replaceChildren(signature(data))) : empty("待复核员签署。"));
  const options = el("select", {"aria-label": "选择已完成的批次", onchange: event => {
    location.hash = `evidence/${event.target.value}`;
  }}, runs.map(item => el("option", {value: item.id, selected: item.id === run.id}, `#${item.id} ${item.case_title}`)));
  const result = run.result;
  const handovers = result.handovers || [];
  const inService = result.in_service || [];
  const held = holds(result.rows);
  return el("div", {class: "page evidence"},
    pageHeading(config.modules[3], run.case_title, button),
    issue, options,
    el("section", {class: "feature evidence-summary"}, el("div", {}, el("h2", {}, "批次判定"), el("p", {}, result.summary)),
      el("details", {}, el("summary", {}, "证据摘要"), el("code", {}, run.digest))),
    el("dl", {class: "metrics"}, Object.entries(result.metrics).map(([label, value]) =>
      el("div", {}, el("dt", {}, label), el("dd", {}, cell(value))))),
    section("实际生效的交接", handovers.length ? handoverTable(handovers) : empty("本批没有接替关系的交接。")),
    section("搁置原因", held.length ?
      table(["站号", "片区", "决定", "原因"], held.map(row => [row["站号"], row["片区"], row["决定"], row["原因"]]), "搁置原因") :
      empty("本批没有搁置站点。")),
    section("在役名册", inService.length ? inServiceTable(inService) : empty("在役名册为空。")),
    section("业务结果明细", result.rows.length ? resultTable(result.rows) : empty("此批次无明细。")),
    section("复核签署", signing));
}
