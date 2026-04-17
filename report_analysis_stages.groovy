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

        echo "Previous build: #${env.PREV_BUILD_NUM}"
        echo "Previous report URL: ${env.PREVIOUS_REPORT_URL}"
        echo "Current build: #${env.BUILD_NUMBER}"
        env.CURRENT_REPORT_URL = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/Test_5freport/"

        sh '''
            if [ "${SKIP_ANALYSIS}" = "true" ]; then
                echo "Skipping report analysis - no previous build"
                exit 0
            fi

            mkdir -p ${REPORT_OUTPUT_DIR}

            # Generate git diff JSON using GIT_PREVIOUS_SUCCESSFUL_COMMIT (set by Jenkins Git plugin)
            PREV_COMMIT="${GIT_PREVIOUS_SUCCESSFUL_COMMIT:-}"
            CURR_COMMIT="${GIT_COMMIT:-HEAD}"
            GIT_DIFF_ARG=""

            if [ -z "$PREV_COMMIT" ]; then
                echo "No previous successful commit found, skipping git diff"
            elif [ "$PREV_COMMIT" = "$CURR_COMMIT" ]; then
                echo "Same commit ($CURR_COMMIT), skipping git diff"
            else
                echo "Git diff: $PREV_COMMIT -> $CURR_COMMIT"
                cd ${WORKSPACE}/nd_test_bot

                python3 -c "
import json, subprocess, sys

prev_commit = sys.argv[1]
curr_commit = sys.argv[2]
output_path = sys.argv[3]

def get_tc_files(diff_filter):
    result = subprocess.run(
        ['git', 'diff', '--diff-filter=' + diff_filter, '--name-only', prev_commit + '..' + curr_commit],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().splitlines() if '/TC' in f or f.startswith('TC')]

added = get_tc_files('A')
modified = get_tc_files('M')

data = {
    'prev_commit': prev_commit,
    'curr_commit': curr_commit,
    'tc_files_added': len(added),
    'tc_files_modified': len(modified),
    'added_files': added,
    'modified_files': modified
}
with open(output_path, 'w') as f:
    json.dump(data, f, indent=2)
print('Git diff JSON: {} TC added, {} TC modified'.format(len(added), len(modified)))
" "$PREV_COMMIT" "$CURR_COMMIT" "${REPORT_OUTPUT_DIR}/git_diff.json"

                GIT_DIFF_ARG="--git-diff-json ${REPORT_OUTPUT_DIR}/git_diff.json"
            fi

            source /home/deviceqa/DTA_venv/nd_test_bot_env/bin/activate
            pip install -r ''' + reportAnalysisPath + '''/requirements.txt

            cd ''' + reportAnalysisPath + '''
            python3 analyze.py \
                --previous "${PREVIOUS_REPORT_URL}" \
                --current "${CURRENT_REPORT_URL}" \
                --output-html "${REPORT_OUTPUT_DIR}/comparison_report.html" \
                --output-json "${REPORT_OUTPUT_DIR}/comparison_report.json" \
                $GIT_DIFF_ARG
        '''
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
