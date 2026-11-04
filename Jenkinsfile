// Publish once for all suites; also called from post if a preceding stage fails.
def publishResults(String root) {
    try {
        junit testResults: "${root}/*/junit.xml", allowEmptyResults: false
    } finally {
        def resultPaths = []
        for (suite in ['api', 'web', 'mobile']) {
            if (fileExists("${root}/${suite}/allure-results")) {
                resultPaths.add([path: "${root}/${suite}/allure-results"])
            }
        }
        if (resultPaths) {
            // History is prepared outside WORKSPACE. Allure only changes a transaction copy.
            def helper = '@.venv\\Scripts\\python.exe ci\\allure_history.py '
            def historyRoot = params.ALLURE_HISTORY_DIR?.trim()
            if (!historyRoot) {
                def rootCode = bat(returnStatus: true,
                    script: helper + 'default-root > "' + root + '/history-root.txt"')
                if (rootCode == 0) {
                    historyRoot = readFile(file: "${root}/history-root.txt", encoding: 'UTF-8').trim()
                }
            }
            def historyFile = null
            withEnv(["ALLURE_HISTORY_DIR=${historyRoot ?: ''}"]) {
                if (historyRoot && bat(returnStatus: true, script: helper + 'probe') == 0) {
                    def inputs = resultPaths.collect { '"' + it.path + '"' }.join(' ')
                    def prepareCode = bat(returnStatus: true,
                        script: helper + 'prepare --results ' + inputs + ' > "' + root + '/history-path.txt"')
                    if (prepareCode == 0) {
                        historyFile = readFile(file: "${root}/history-path.txt", encoding: 'UTF-8').trim()
                    }
                }
                if (!historyFile) {
                    // Preserve JUnit/Allure publication, but make persistence failure visible.
                    unstable('Allure history unavailable; publishing current results without history.')
                }
                withEnv(["ALLURE_HISTORY_PATH=${historyFile ?: ''}"]) {
                    allure commandline: 'allure', configPath: 'allurerc.mjs', includeProperties: false,
                           reportBuildPolicy: 'ALWAYS', results: resultPaths
                }
                // This code is not reached if generation throws or the build is interrupted.
                if (historyFile) {
                    def transaction = historyFile.substring(0, historyFile.lastIndexOf('\\'))
                    withEnv(["ALLURE_HISTORY_TRANSACTION=${transaction}"]) {
                        def commitCode = bat(returnStatus: true,
                            script: helper + 'commit --transaction "%ALLURE_HISTORY_TRANSACTION%"')
                        if (commitCode != 0) {
                            unstable('Allure generated; history commit failed. Previous snapshots preserved.')
                        } else if (bat(returnStatus: true,
                            script: helper + 'export --output "' + root + '/history-snapshot"') != 0) {
                            unstable('Allure history committed; snapshot archive export failed.')
                        }
                    }
                }
            }
        } else {
            echo 'Allure results are unavailable; check pytest startup errors.'
        }
    }
}

pipeline {
    agent { label 'windows-api' }

    triggers {
        pollSCM('H/5 * * * *')
    }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
    }

    parameters {
        string(name: 'PYTHON_EXE', defaultValue: 'C:\\Users\\user\\AppData\\Local\\Python\\bin\\python.exe',
               description: 'Python 3.14 executable available to the Windows agent service; absolute path recommended.')
        string(name: 'ANDROID_AVD', defaultValue: 'Pixel_4',
               description: 'Existing AVD to start automatically if emulator-5554 is absent.')
        string(name: 'ALLURE_HISTORY_DIR', defaultValue: '',
               description: 'Persistent history root outside WORKSPACE. Empty uses agent LOCALAPPDATA/QA-Guru/allure-history.')
    }

    environment {
        PYTHONUTF8 = '1'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                script {
                    def scmInfo = checkout scm
                    env.QA_HISTORY_BRANCH = scmInfo.GIT_BRANCH ?: env.BRANCH_NAME ?: ''
                }
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
        stage('Prepare Mobile environment') {
            steps {
                bat 'ci\\run-mobile.cmd Prepare'
            }
        }
        stage('Mobile tests') {
            steps {
                timeout(time: 16, unit: 'MINUTES') {
                    script {
                        def code
                        withEnv(["REPORT_ROOT=${env.REPORT_ROOT}/mobile",
                                 'START_ANDROID_EMULATOR=true',
                                 "ANDROID_AVD=${params.ANDROID_AVD}"]) {
                            code = bat(returnStatus: true, script: 'ci\\run-mobile.cmd Test')
                        }
                        if (code == 1) {
                            unstable('Mobile tests failed; see JUnit results.')
                        } else if (code != 0) {
                            error("Mobile infrastructure/pytest error: exit ${code}")
                        }
                    }
                }
            }
        }
        stage('Publish results') {
            steps {
                script {
                    for (suite in ['api', 'web', 'mobile']) {
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
