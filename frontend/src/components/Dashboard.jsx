import React from "react";
import { motion } from "framer-motion";
import ConfidenceGauge from "./ConfidenceGauge";
import RiskHeatmap from "./RiskHeatmap";
import TestCaseTable from "./TestCaseTable";
import DeploymentVerdict from "./DeploymentVerdict";

export default function Dashboard({ data }) {
  if (!data) return null;

  const { defects, tests } = data;

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="flex flex-col gap-6"
    >
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <ConfidenceGauge
            score={defects.overall_confidence_score}
            recommendation={defects.deployment_recommendation}
          />
        </div>
        <div className="lg:col-span-2">
          <RiskHeatmap moduleRisks={defects.module_risks} />
        </div>
      </div>
      <TestCaseTable tests={tests} criticalIds={defects.critical_test_ids} />
      <DeploymentVerdict
        recommendation={defects.deployment_recommendation}
        rationale={defects.recommendation_rationale}
      />
    </motion.div>
  );
}
