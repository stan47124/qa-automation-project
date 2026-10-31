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
                }
            }
        }
        stage('API tests') {
            steps {
                script {
                    def code = bat(returnStatus: true, script: 'ci\\run-api.cmd Test')
                    if (code == 1) {
                        unstable('API tests failed; see JUnit results.')
                    } else if (code != 0) {
                        error("pytest infrastructure/collection error: exit ${code}")
                    }
                }
            }
            post {
                always {
                    script {
                        // Attempt both publishers even if JUnit is missing or invalid.
                        try {
                            junit testResults: "${env.REPORT_ROOT}/junit.xml", allowEmptyResults: false
                        } finally {
                            if (fileExists("${env.REPORT_ROOT}/allure-results")) {
                                allure commandline: 'allure', includeProperties: false,
                                       reportBuildPolicy: 'ALWAYS',
                                       results: [[path: "${env.REPORT_ROOT}/allure-results"]]
                            } else {
                                echo 'Allure results are unavailable; check pytest startup errors.'
                            }
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            script {
                if (env.REPORT_ROOT?.trim()) {
                    archiveArtifacts artifacts: "${env.REPORT_ROOT}/**", allowEmptyArchive: true
                }
            }
        }
    }
}
