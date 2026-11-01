// Publish once for both suites; also called from post if a preceding stage fails.
def publishResults(String root) {
    try {
        junit testResults: "${root}/*/junit.xml", allowEmptyResults: false
    } finally {
        def resultPaths = []
        for (suite in ['api', 'web']) {
            if (fileExists("${root}/${suite}/allure-results")) {
                resultPaths.add([path: "${root}/${suite}/allure-results"])
            }
        }
        if (resultPaths) {
            allure commandline: 'allure', includeProperties: false,
                   reportBuildPolicy: 'ALWAYS', results: resultPaths
        } else {
            echo 'Allure results are unavailable; check pytest startup errors.'
        }
    }
}

pipeline {
    agent { label 'windows-api' }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
    }

    parameters {
        string(name: 'PYTHON_EXE', defaultValue: 'C:\\Users\\user\\AppData\\Local\\Python\\bin\\python.exe',
               description: 'Python 3.14 executable available to the Windows agent service; absolute path recommended.')
    }

    environment {
        PYTHONUTF8 = '1'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Prepare API environment') {
            steps {
                script {
                    withEnv(["PYTHON_EXE=${params.PYTHON_EXE}"]) {
                        bat 'ci\\run-api.cmd Prepare'
                    }
                }
                script {
                    env.REPORT_ROOT = bat(returnStdout: true, script: '''@.venv\\Scripts\\python.exe -c "import os, uuid; print('artifacts/jenkins-' + os.environ['BUILD_NUMBER'] + '-' + uuid.uuid4().hex)"''').trim()
                    env.QA_RESULTS_PUBLISHED = 'false'
                }
            }
        }
        stage('API tests') {
            steps {
                script {
                    def code
                    withEnv(["REPORT_ROOT=${env.REPORT_ROOT}/api"]) {
                        code = bat(returnStatus: true, script: 'ci\\run-api.cmd Test')
                    }
                    if (code == 1) {
                        unstable('API tests failed; see JUnit results.')
                    } else if (code != 0) {
                        error("pytest infrastructure/collection error: exit ${code}")
                    }
                }
            }
        }
        stage('Prepare Web UI environment') {
            steps {
                bat 'ci\\run-web.cmd Prepare'
            }
        }
        stage('Web UI tests') {
            steps {
                script {
                    def code
                    withEnv(['HEADLESS=true', "REPORT_ROOT=${env.REPORT_ROOT}/web"]) {
                        code = bat(returnStatus: true, script: 'ci\\run-web.cmd Test')
                    }
                    if (code == 1) {
                        unstable('Web UI tests failed; see JUnit results.')
                    } else if (code != 0) {
                        error("Web UI pytest infrastructure/collection error: exit ${code}")
                    }
                }
            }
        }
        stage('Publish results') {
            steps {
                script {
                    for (suite in ['api', 'web']) {
                        if (!fileExists("${env.REPORT_ROOT}/${suite}/junit.xml")) {
                            error("Missing ${suite} JUnit XML; available reports will be published in post.")
                        }
                    }
                    // Mark before publishing so a publisher failure does not generate a second report.
                    env.QA_RESULTS_PUBLISHED = 'true'
                    publishResults(env.REPORT_ROOT)
                }
            }
        }
    }

    post {
        always {
            script {
                if (env.REPORT_ROOT?.trim()) {
                    try {
                        if (env.QA_RESULTS_PUBLISHED != 'true') {
                            publishResults(env.REPORT_ROOT)
                        }
                    } finally {
                        archiveArtifacts artifacts: "${env.REPORT_ROOT}/**", allowEmptyArchive: true
                    }
                }
            }
        }
    }
}
