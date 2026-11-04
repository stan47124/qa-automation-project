import java.io.File;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

/** Read-only compatibility probe against the agent's actual cached plugin JARs. */
public class CheckAllurePlugin {
    public static void main(String[] args) throws Exception {
        Class<?> builderType = Class.forName("org.allurereport.jenkins.ReportBuilder");
        Class<?> fileType = Class.forName("hudson.FilePath");
        Class<?> argumentsType = Class.forName("hudson.util.ArgumentListBuilder");
        var constructor = Arrays.stream(builderType.getConstructors())
                .filter(value -> value.getParameterCount() == 6).findFirst().orElseThrow();
        Object builder = constructor.newInstance(null, null, null, null, null, "3.16.0");
        Object config = fileType.getConstructor(File.class).newInstance(new File("allurerc.mjs"));
        Object results = fileType.getConstructor(File.class).newInstance(new File("probe-results"));
        Object output = fileType.getConstructor(File.class).newInstance(new File("probe-output"));
        builderType.getMethod("setConfigFilePath", fileType).invoke(builder, config);
        Object command = argumentsType.getConstructor().newInstance();
        Method append = builderType.getDeclaredMethod("appendAllure3Arguments", argumentsType, List.class, fileType);
        append.setAccessible(true);
        append.invoke(builder, command, List.of(results), output);
        @SuppressWarnings("unchecked")
        List<String> values = (List<String>) argumentsType.getMethod("toList").invoke(command);
        if (!values.get(0).equals("generate") || !values.contains("--config")
                || !values.get(values.indexOf("--config") + 1).endsWith("allurerc.mjs")
                || values.contains("--clean")) {
            throw new IllegalStateException("Allure 3 configPath command not supported");
        }
        Class<?> publisher = Class.forName("org.allurereport.jenkins.AllureReportPublisher");
        boolean bindable = Arrays.stream(publisher.getMethod("setConfigPath", String.class).getAnnotations())
                .anyMatch(value -> value.annotationType().getName().equals("org.kohsuke.stapler.DataBoundSetter"));
        if (!bindable) throw new IllegalStateException("configPath is not a data-bound parameter");
        System.out.println("Plugin " + builderType.getPackage().getImplementationVersion()
                + ": configPath -> Allure 3 generate --config: PASS; no Jenkins calls or processes launched");
    }
}
