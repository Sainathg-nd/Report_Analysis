/**
 * Reusable Report Analysis stages for Jenkins pipelines.
 *
 * Place this file at the same static path as the Report_Analysis scripts
 * (e.g., /home/deviceqa/Report_Analysis/report_analysis_stages.groovy).
 *
 * Usage in any pipeline — only 3 changes needed:
 *
 *   1) Add these parameters to your pipeline's parameters block:
 *
 *        booleanParam(name: 'enable_report_analysis', defaultValue: true, description: 'Enable comparison analysis against previous build')
 *        string(name: 'report_analysis_path', defaultValue: '/home/deviceqa/Report_Analysis', description: 'Static path to Report_Analysis scripts on the agent')
 *        string(name: 'prev_build_number', defaultValue: '', description: 'Previous build number to compare against (leave empty for auto-detect)')
 *
 *   2) Add a single stage after Publish_Test_Report:
 *
 *        stage('Report_Analysis') {
 *            when {
 *                expression { return params.enable_report_analysis }
 *            }
 *            steps {
 *                script {
 *                    def reportAnalysis = load "${params.report_analysis_path}/report_analysis_stages.groovy"
 *                    reportAnalysis.run(
 *                        port: params.port,
 *                        branch: params.branch,
 *                        reportAnalysisPath: params.report_analysis_path,
 *                        prevBuildNumber: params.prev_build_number
 *                    )
 *                }
 *            }
 *        }
 *
 *   3) Add this line in your post > success email body (after the Test_Automation_Report link):
 *
 *        <p>Report comparison available at <a href='${reportUrl}Report_5fComparison/'>Report_Comparison</a></p>
 *
 * That's it. The groovy file handles: report comparison, git diff, packaging,
 * archiving the tarball, and publishing the HTML report to Jenkins.
 */

def run(Map config) {
    def port = config.port
    def branch = config.branch
    def reportAnalysisPath = config.reportAnalysisPath ?: '/home/deviceqa/Report_Analysis'
    def prevBuildNumber = config.prevBuildNumber ?: ''

    // ── Stage 1: Run Report Analysis ──────────────────────────────────
    stage('Run_Report_Analysis') {
        if (prevBuildNumber?.trim()) {
            env.PREV_BUILD_NUM = prevBuildNumber.trim()
        } else {
            def prevBuild = currentBuild.previousSuccessfulBuild
            if (prevBuild) {
                env.PREV_BUILD_NUM = prevBuild.number.toString()
            } else {
                echo "No previous successful build found, skipping report analysis"
                env.SKIP_ANALYSIS = 'true'
                return
            }
        }
        env.SKIP_ANALYSIS = 'false'
        env.CURRENT_REPORT_DIR = "${env.WORKSPACE}/nd_test_bot/Test_Automation_Framework/Output/report/127.0.0.1:${port}"
        env.PREVIOUS_REPORT_URL = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.PREV_BUILD_NUM}/Test_5freport/"
        env.REPORT_OUTPUT_DIR = "${env.WORKSPACE}/report_analysis_output"
        env.REPORT_ANALYSIS_PATH = reportAnalysisPath

        echo "Previous build: #${env.PREV_BUILD_NUM}"
        echo "Previous report URL: ${env.PREVIOUS_REPORT_URL}"
        echo "Current build: #${env.BUILD_NUMBER}"
        env.CURRENT_REPORT_URL = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/Test_5freport/"

        // Get the commit from the previous successful build for git diff
        def prevCommit = ''
        def prevBuild2 = currentBuild.previousSuccessfulBuild
        if (prevBuild2) {
            prevCommit = prevBuild2.buildVariables?.get('GIT_COMMIT') ?: ''
            if (!prevCommit?.trim()) {
                try {
                    prevCommit = prevBuild2.rawBuild?.getEnvironment(hudson.model.TaskListener.NULL)?.get('GIT_COMMIT') ?: ''
                } catch (e) {
                    echo "Could not retrieve previous build commit: ${e.message}"
                }
            }
        }

        def gitDiffArg = ''
        if (prevCommit?.trim()) {
            echo "Previous build commit: ${prevCommit}"
            echo "Current build commit:  ${env.GIT_COMMIT}"
            env.PREV_COMMIT = prevCommit
            gitDiffArg = "--git-diff-json \${REPORT_OUTPUT_DIR}/git_diff.json"
        } else {
            echo "No previous build commit found, skipping git diff"
        }

        sh """
            if [ "\${SKIP_ANALYSIS}" = "true" ]; then
                echo "Skipping report analysis - no previous build"
                exit 0
            fi

            mkdir -p \${REPORT_OUTPUT_DIR}

            # Generate git diff JSON if previous commit is available
            if [ -n "${prevCommit}" ]; then
                cd \${WORKSPACE}/nd_test_bot

                ADDED_FILES=\$(git diff --diff-filter=A --name-only ${prevCommit}..HEAD | grep '/TC\\|^TC' || true)
                MODIFIED_FILES=\$(git diff --diff-filter=M --name-only ${prevCommit}..HEAD | grep '/TC\\|^TC' || true)
                TC_ADDED=\$(echo "\$ADDED_FILES" | grep -c '.' || echo 0)
                TC_MODIFIED=\$(echo "\$MODIFIED_FILES" | grep -c '.' || echo 0)

                # Build JSON using python for safe serialization
                python3 -c "
import json, sys
added = [f for f in '''\\${ADDED_FILES}'''.strip().splitlines() if f.strip()]
modified = [f for f in '''\\${MODIFIED_FILES}'''.strip().splitlines() if f.strip()]
data = {
    'prev_commit': '${prevCommit}',
    'curr_commit': '\${GIT_COMMIT:-HEAD}',
    'tc_files_added': len(added),
    'tc_files_modified': len(modified),
    'added_files': added,
    'modified_files': modified
}
with open('\${REPORT_OUTPUT_DIR}/git_diff.json', 'w') as f:
    json.dump(data, f, indent=2)
print('Git diff JSON generated')
"
            fi

            source /home/deviceqa/DTA_venv/nd_test_bot_env/bin/activate
            pip install -r ${reportAnalysisPath}/requirements.txt

            cd ${reportAnalysisPath}
            python3 analyze.py \\
                --previous "\${PREVIOUS_REPORT_URL}" \\
                --current "\${CURRENT_REPORT_URL}" \\
                --output-html "\${REPORT_OUTPUT_DIR}/comparison_report.html" \\
                --output-json "\${REPORT_OUTPUT_DIR}/comparison_report.json" \\
                ${prevCommit?.trim() ? '--git-diff-json "\${REPORT_OUTPUT_DIR}/git_diff.json"' : ''}
        """
    }

    if (env.SKIP_ANALYSIS == 'true') {
        echo "Skipping packaging and publishing - no previous build"
        return
    }

    // ── Stage 2: Package, Archive & Publish ───────────────────────────
    stage('Package_and_Publish_Analysis') {
        sh """
            cd \${REPORT_OUTPUT_DIR}
            tar -czf \${WORKSPACE}/report_analysis_output.tar.gz \\
                comparison_report.html comparison_report.json \\
                \$([ -f git_diff.json ] && echo git_diff.json || true)
        """

        archiveArtifacts artifacts: 'report_analysis_output.tar.gz', allowEmptyArchive: true

        publishHTML(target: [
            allowMissing: true,
            alwaysLinkToLastBuild: true,
            keepAll: true,
            reportDir: 'report_analysis_output',
            reportFiles: 'comparison_report.html',
            reportName: 'Report_Comparison',
            reportTitles: 'Report_Comparison'
        ])
    }
}

return this
