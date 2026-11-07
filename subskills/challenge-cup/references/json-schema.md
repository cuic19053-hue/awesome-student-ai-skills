# 十九、JSON Schema 定义（v2.1 必加章节 9）

> 从 `subskills/challenge-cup/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 19.1 完整 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "挑战杯申报书数据",
  "type": "object",
  "required": [
    "work_full_name", "work_type", "applicant_type", "leader_name",
    "leader_id", "college", "school", "apply_date", "abstract",
    "background", "research_method", "results_discussion", "conclusion",
    "innovations", "policy_citations", "scientific_challenges",
    "literature_review", "economic_benefits", "defense_ppt"
  ],
  "properties": {
    "work_full_name": {
      "type": "string",
      "maxLength": 30,
      "description": "作品全称，≤30 字"
    },
    "work_type": {
      "type": "string",
      "enum": ["natural_science", "social_science", "tech_invention"],
      "description": "三大类别"
    },
    "category": {
      "type": "string",
      "enum": ["natural_science", "social_science", "tech_invention"],
      "description": "与 work_type 等价（兼容旧字段）"
    },
    "applicant_type": {
      "type": "string",
      "enum": ["individual", "collective"]
    },
    "leader_name": {"type": "string"},
    "leader_id": {"type": "string"},
    "leader_major": {"type": "string"},
    "leader_grade": {"type": "string"},
    "leader_gender": {"type": "string"},
    "leader_age": {"type": "string"},
    "leader_phone": {"type": "string"},
    "college": {"type": "string"},
    "school": {"type": "string"},
    "apply_date": {"type": "string"},
    "discipline": {"type": "string"},
    "duration": {"type": "string"},
    "advisor_name": {"type": "string"},
    "advisor_title": {"type": "string"},
    "advisor_research": {"type": "string"},
    "advisor_phone": {"type": "string"},
    "team_members": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "id": {"type": "string"},
          "major": {"type": "string"},
          "grade": {"type": "string"},
          "role": {"type": "string"}
        }
      },
      "maxItems": 7
    },
    "abstract": {
      "type": "string",
      "maxLength": 500,
      "description": "作品简介，≤500 字"
    },
    "background": {
      "type": "array",
      "items": {"type": "string"},
      "description": "选题背景与意义，4 子节"
    },
    "research_method": {
      "type": "array",
      "items": {"type": "string"},
      "description": "研究方法与过程，4 子节"
    },
    "results_discussion": {
      "type": "array",
      "items": {"type": "string"},
      "description": "研究结果与讨论，4 子节"
    },
    "conclusion": {
      "type": "string",
      "description": "结论，400~600 字"
    },
    "innovations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "type": {"type": "string"},
          "description": {"type": "string"},
          "advantage": {"type": "string"}
        }
      },
      "minItems": 3,
      "maxItems": 5
    },
    "references": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "authors": {"type": "string"},
          "title": {"type": "string"},
          "type": {"type": "string"},
          "source": {"type": "string"},
          "year": {"type": "string"},
          "volume": {"type": "string"},
          "issue": {"type": "string"},
          "pages": {"type": "string"},
          "publisher": {"type": "string"},
          "city": {"type": "string"}
        }
      },
      "minItems": 5
    },
    "appendix": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "content": {"type": "string"}
        }
      }
    },

    "policy_citations": {
      "type": "array",
      "minItems": 8,
      "description": "国家政策引用，≥8 项",
      "items": {
        "type": "object",
        "properties": {
          "issuer": {"type": "string"},
          "doc_no": {"type": "string"},
          "title": {"type": "string"},
          "publish_date": {"type": "string"},
          "key_excerpt": {"type": "string"},
          "relevance": {"type": "string"}
        },
        "required": ["issuer", "title", "publish_date", "key_excerpt"]
      }
    },
    "scientific_challenges": {
      "type": "array",
      "minItems": 3,
      "maxItems": 3,
      "description": "科学挑战，严格 3 段",
      "items": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "description": {"type": "string"},
          "sub_challenges": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "title": {"type": "string"},
                "detail": {"type": "string"},
                "reference": {"type": "string"}
              }
            }
          }
        }
      }
    },
    "literature_review": {
      "type": "array",
      "description": "国内外研究现状综述，30+ 文献",
      "items": {
        "type": "object",
        "properties": {
          "section": {"type": "string"},
          "topic": {"type": "string"},
          "citations": {"type": "array", "items": {"type": "string"}},
          "content": {"type": "string"}
        }
      }
    },
    "algorithm_comparison": {
      "type": "object",
      "properties": {
        "title": {"type": "string"},
        "dimensions": {"type": "array", "items": {"type": "string"}},
        "algorithms": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "ref": {"type": "string"},
              "values": {"type": "array", "items": {"type": "string"}}
            }
          }
        },
        "conclusion": {"type": "string"}
      }
    },
    "tech_roadmap": {
      "type": "array",
      "minItems": 3,
      "description": "技术路线图，≥3 张",
      "items": {
        "type": "object",
        "properties": {
          "figure_no": {"type": "string"},
          "title": {"type": "string"},
          "nodes": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": {"type": "string"},
                "label": {"type": "string"}
              }
            }
          },
          "edges": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "from": {"type": "string"},
                "to": {"type": "string"}
              }
            }
          },
          "description": {"type": "string"}
        }
      }
    },
    "formulas": {
      "type": "array",
      "description": "数学公式，自然/发明类必备",
      "items": {
        "type": "object",
        "properties": {
          "equation_no": {"type": "string"},
          "expression": {"type": "string"},
          "variables": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "symbol": {"type": "string"},
                "meaning": {"type": "string"}
              }
            }
          },
          "context": {"type": "string"}
        }
      }
    },
    "economic_benefits": {
      "type": "array",
      "minItems": 10,
      "description": "社会经济效益量化，≥10 项",
      "items": {
        "type": "object",
        "properties": {
          "indicator": {"type": "string"},
          "traditional_baseline": {"type": "string"},
          "system_expected": {"type": "string"},
          "improvement": {"type": "string"}
        }
      }
    },
    "defense_ppt": {
      "type": "array",
      "minItems": 10,
      "maxItems": 10,
      "description": "答辩 PPT 框架，10 页",
      "items": {
        "type": "object",
        "properties": {
          "slide_no": {"type": "integer"},
          "title": {"type": "string"},
          "duration": {"type": "string"},
          "key_points": {"type": "array", "items": {"type": "string"}},
          "visual": {"type": "string"},
          "speaker_notes": {"type": "string"}
        }
      }
    }
  }
}
```

### 19.2 字段速查表

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| work_full_name | str | P0 | - | 作品全称 ≤30 字 |
| work_type | str | P0 | - | 三大类代码 |
| applicant_type | str | P0 | collective | individual/collective |
| leader_name | str | P0 | - | 申报者代表姓名 |
| leader_id | str | P0 | - | 学号 |
| leader_major | str | P0 | - | 专业 |
| leader_grade | str | P0 | - | 年级 |
| college | str | P0 | - | 学院 |
| school | str | P0 | - | 学校 |
| apply_date | str | P0 | - | 申报日期 |
| abstract | str | P0 | - | 作品简介 ≤500 字 |
| background | list | P0 | - | 选题背景 4 子节 |
| research_method | list | P0 | - | 研究方法 4 子节 |
| results_discussion | list | P0 | - | 研究结果 4 子节 |
| conclusion | str | P0 | - | 结论 400~600 字 |
| innovations | list | P0 | - | 创新点 3~5 个 |
| policy_citations | list | P0（v2.1） | - | 政策引用 ≥8 |
| scientific_challenges | list | P0（v2.1） | - | 科学挑战 3 段 |
| literature_review | list | P0（v2.1） | - | 文献综述 30+ |
| algorithm_comparison | obj | P1（v2.1） | - | 算法对比表 |
| tech_roadmap | list | P0（v2.1） | - | 技术路线 3 张 |
| formulas | list | P0（v2.1） | - | 公式（自然/发明类） |
| economic_benefits | list | P0（v2.1） | - | 经济效益 10 项 |
| defense_ppt | list | P0（v2.1） | - | 答辩 PPT 10 页 |
| references | list | P1 | - | 参考文献 |
| appendix | list | P1 | - | 附录清单 |

---

