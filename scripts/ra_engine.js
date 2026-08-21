/* ra_engine.js — a faithful mirror of reg_advisor/scripts/regadvisor_engine.py.
   reg_advisor is the single source of truth; this file re-implements eval_term,
   check_prereqs, carry_ok, unmet_count and the four-bucket verdict exactly, so
   the explorer page agrees with the advisor. build_explorer.py embeds parity
   cases computed by the PYTHON engine; the page re-runs them and reports parity.

   Kept as a plain script (assigned onto window) so it drops straight into the
   single-file page — no modules, no build step of its own. */
(function(root){
"use strict";

var DEFAULT_CORE_LEN = 7;

function coreCode(code, length){
  var s = code == null ? "" : String(code).trim();
  var n = (!length || length <= 0) ? DEFAULT_CORE_LEN : length;
  if(s.length <= n || !/^[A-Za-z0-9]+$/.test(s)) return s;
  return s.slice(0, n);
}
function codeLevel(code){
  var m = /[A-Za-z]+(\d)/.exec(String(code));
  return m ? parseInt(m[1], 10) : 0;
}
function has(tx, code){ return tx.passed_set.has(coreCode(code, tx.core_len)); }
function best(tx, code){ return tx.best[coreCode(code, tx.core_len)] || null; }

/* eval_term — returns {met, soft, label, missing:[...]} */
function evalTerm(term, tx){
  if(term == null) return {met:true, soft:false, label:"", missing:[]};
  if(typeof term === "string"){
    var ok = has(tx, term);
    return {met:ok, soft:false, label:term, missing:ok?[]:[term]};
  }
  if(Array.isArray(term)) return evalTerm({all:term}, tx);

  if("all" in term){
    var rs = term.all.map(function(t){ return evalTerm(t, tx); });
    var hard = rs.filter(function(r){ return !r.soft; });
    return {met:hard.every(function(r){ return r.met; }), soft:false,
            label:rs.map(function(r){ return r.label; }).join(" & "),
            missing:hard.filter(function(r){ return !r.met; })
                        .reduce(function(a,r){ return a.concat(r.missing); }, [])};
  }
  if("any" in term){
    var ra = term.any.map(function(t){ return evalTerm(t, tx); });
    var metA = ra.some(function(r){ return r.met; });
    return {met:metA, soft:false,
            label:"(" + ra.map(function(r){ return r.label; }).join(" | ") + ")",
            missing:metA?[]:ra.reduce(function(a,r){ return a.concat(r.missing); }, [])};
  }
  if("any_n" in term && "of" in term){
    var rn = term.of.map(function(t){ return evalTerm(t, tx); });
    var metN = rn.filter(function(r){ return r.met; }).length >= term.any_n;
    return {met:metN, soft:false,
            label:term.any_n + "-of-(" + rn.map(function(r){ return r.label; }).join(", ") + ")",
            missing:metN?[]:rn.filter(function(r){ return !r.met; })
                               .reduce(function(a,r){ return a.concat(r.missing); }, [])};
  }
  if("review" in term){
    return {met:false, soft:false, label:"[review: " + term.review + "]",
            missing:["review:" + term.review]};
  }
  if("min_year" in term){
    var oky = (tx.year_of_study || 0) >= term.min_year;
    return {met:oky, soft:false, label:"year>=" + term.min_year,
            missing:oky?[]:["year>=" + term.min_year]};
  }
  if("min_sem" in term){
    var oks = (tx.semesters_registered || 0) >= term.min_sem;
    return {met:oks, soft:false, label:"sem>=" + term.min_sem,
            missing:oks?[]:["sem>=" + term.min_sem]};
  }
  if("min_credits" in term){
    var lv = ("level" in term) ? term.level : null;
    var have = lv != null ? (tx.credits_by_level[lv] || 0) : (tx.credits_passed || 0);
    var okc = have >= term.min_credits;
    var lab = ">=" + term.min_credits + "cr" + (lv != null ? " L" + lv : "");
    return {met:okc, soft:false, label:lab, missing:okc?[]:[lab]};
  }
  if("code" in term){
    if(term.soft){
      return {met:true, soft:true, label:term.code + " (rec)",
              missing:has(tx, term.code)?[]:[term.code]};
    }
    var b = best(tx, term.code);
    if(term.min_mark != null){
      var mm = term.min_mark, okm;
      if(b == null) okm = false;
      else if(b.mark != null) okm = b.mark >= mm;
      else okm = b.passed;
      return {met:okm, soft:false, label:term.code + ">=" + mm,
              missing:okm?[]:[term.code]};
    }
    var okp = has(tx, term.code);
    return {met:okp, soft:false, label:term.code, missing:okp?[]:[term.code]};
  }
  return {met:true, soft:false, label:"", missing:[]};
}

function unmetCount(term, tx){
  if(evalTerm(term, tx).met) return 0;
  if(Array.isArray(term)) term = {all:term};
  if(term && typeof term === "object"){
    if("all" in term) return term.all.reduce(function(a,t){ return a + unmetCount(t, tx); }, 0);
    if("any" in term) return 1;
    if("any_n" in term && "of" in term){
      var met = term.of.filter(function(t){ return evalTerm(t, tx).met; }).length;
      return Math.max(1, term.any_n - met);
    }
  }
  return 1;
}

function carryOk(term, tx, floor){
  if(floor == null) floor = 45;
  if(evalTerm(term, tx).met) return true;
  if(Array.isArray(term)) term = {all:term};
  var code = null;
  if(term && typeof term === "object"){
    if("all" in term) return term.all.every(function(t){ return carryOk(t, tx, floor); });
    if("any" in term) return term.any.some(function(t){ return carryOk(t, tx, floor); });
    if("any_n" in term && "of" in term)
      return term.of.filter(function(t){ return carryOk(t, tx, floor); }).length >= term.any_n;
    code = term.code;
  } else if(typeof term === "string"){ code = term; }
  if(!code) return false;
  var b = best(tx, code);
  return !!(b && b.mark != null && b.mark > floor);
}

function checkPrereqs(mod, tx){
  var pr = mod.prereqs || [];
  if(!pr.length) return {met:true, missing:[], unmet:[], soft:[], n_unmet:0};
  var paired = pr.map(function(t){ return [t, evalTerm(t, tx)]; });
  var hard = paired.filter(function(p){ return !p[1].soft; });
  return {
    met: hard.every(function(p){ return p[1].met; }),
    missing: hard.filter(function(p){ return !p[1].met; })
                 .reduce(function(a,p){ return a.concat(p[1].missing); }, []),
    unmet: hard.filter(function(p){ return !p[1].met; }).map(function(p){ return p[1].label; }),
    soft: paired.filter(function(p){ return p[1].soft && p[1].missing.length; })
                .reduce(function(a,p){ return a.concat(p[1].missing); }, []),
    n_unmet: hard.filter(function(p){ return !String(p[1].label).startsWith("[review"); })
                 .reduce(function(a,p){ return a + unmetCount(p[0], tx); }, 0)
  };
}

/* per-module verdict, mirroring eval_advice's branch order */
function verdictFor(mod, tx, rules){
  var c = (rules && rules.concession) || {};
  var gpaFloor = c.min_gpa != null ? c.min_gpa : 55;
  var maxMissing = c.max_missing != null ? c.max_missing : 1;
  var prereqFloor = c.prereq_floor != null ? c.prereq_floor : 45;

  var b = best(tx, mod.code);
  if(b && b.passed) return {verdict:"passed", pc:{met:true, missing:[], unmet:[], soft:[], n_unmet:0}};

  var pc = checkPrereqs(mod, tx);
  var attempted = (tx.attempts[coreCode(mod.code, tx.core_len)] || 0) > 0;
  var hasReview = pc.missing.some(function(m){ return String(m).startsWith("review:"); });
  var carryable = (mod.prereqs || [])
      .filter(function(t){ return !evalTerm(t, tx).soft; })
      .every(function(t){ return carryOk(t, tx, prereqFloor); });

  var v;
  if(pc.met) v = "can_register";
  else if(hasReview) v = "needs_review";
  else if((tx.gpa || 0) >= gpaFloor && pc.n_unmet <= maxMissing && carryable) v = "concession_possible";
  else v = "cannot_register";
  return {verdict:v, pc:pc, repeat:attempted};
}

/* build the transcript index from entered marks (mirror of index_transcript,
   for the single-student, marks-only case the explorer needs) */
function indexMarks(marksByCode, modByCode, passMark, equivalences, coreLen){
  passMark = passMark == null ? 50 : passMark;
  coreLen = coreLen || DEFAULT_CORE_LEN;
  var bestM = {}, attempts = {};
  Object.keys(marksByCode).forEach(function(code){
    var cc = coreCode(code, coreLen);
    var mk = marksByCode[code];
    if(mk == null || isNaN(mk)) return;
    var mod = modByCode[code] || {};
    var passed = mk >= passMark;
    attempts[cc] = (attempts[cc] || 0) + 1;
    bestM[cc] = {code:cc, passed:passed, mark:mk, credits:+(mod.credits || 0)};
  });
  var graded = Object.keys(bestM).map(function(k){ return bestM[k]; })
                     .filter(function(b){ return b.mark != null && b.credits; });
  var wsum = graded.reduce(function(a,b){ return a + b.mark * b.credits; }, 0);
  var wcr  = graded.reduce(function(a,b){ return a + b.credits; }, 0);
  var gpa = wcr ? wsum / wcr : 0;
  var passed_set = new Set(Object.keys(bestM).filter(function(k){ return bestM[k].passed; }));
  var credits_passed = 0, credits_by_level = {};
  Object.keys(bestM).forEach(function(k){
    var b = bestM[k];
    if(b.passed){ credits_passed += b.credits;
      var lv = codeLevel(k); credits_by_level[lv] = (credits_by_level[lv] || 0) + b.credits; }
  });
  (equivalences || []).forEach(function(pair){
    var a = coreCode(pair[0], coreLen), b = coreCode(pair[1], coreLen);
    if(passed_set.has(a) && !passed_set.has(b)){ passed_set.add(b);
      if(!bestM[b]) bestM[b] = Object.assign({}, bestM[a], {code:b}); }
    else if(passed_set.has(b) && !passed_set.has(a)){ passed_set.add(a);
      if(!bestM[a]) bestM[a] = Object.assign({}, bestM[b], {code:a}); }
  });
  return {best:bestM, attempts:attempts, passed_set:passed_set, gpa:gpa,
          credits_passed:credits_passed, credits_by_level:credits_by_level,
          year_of_study:0, semesters_registered:0, core_len:coreLen};
}

root.RA = {coreCode:coreCode, codeLevel:codeLevel, evalTerm:evalTerm,
           unmetCount:unmetCount, carryOk:carryOk, checkPrereqs:checkPrereqs,
           verdictFor:verdictFor, indexMarks:indexMarks};
})(typeof window !== "undefined" ? window : globalThis);
