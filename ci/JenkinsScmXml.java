import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import javax.xml.XMLConstants;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.*;
import org.xml.sax.*;

/** Offline XML 1.0/1.1 processing using the existing JDK, never a Jenkins connection. */
class JenkinsScmXml {
    static final String PROPERTY = "org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty";
    static final String SCM = "hudson.triggers.SCMTrigger";
    static final String SCHEDULE = "H/5 * * * *";

    static Document parse(String text) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new ErrorHandler() {
            public void warning(SAXParseException e) throws SAXException { throw e; }
            public void error(SAXParseException e) throws SAXException { throw e; }
            public void fatalError(SAXParseException e) throws SAXException { throw e; }
        });
        Document document = builder.parse(new InputSource(new StringReader(text)));
        if (!List.of("1.0", "1.1").contains(document.getXmlVersion())) throw new Exception("XML_VERSION");
        return document;
    }

    static List<Element> children(Node parent) {
        List<Element> found = new ArrayList<>();
        if (parent != null) for (Node n = parent.getFirstChild(); n != null; n = n.getNextSibling())
            if (n instanceof Element) found.add((Element)n);
        return found;
    }

    static List<Element> named(Node parent, String name) {
        List<Element> found = new ArrayList<>();
        for (Element e : children(parent)) if (e.getTagName().equals(name)) found.add(e);
        return found;
    }

    static Element one(Node parent, String name) throws Exception {
        List<Element> found = named(parent, name);
        if (found.size() > 1) throw new Exception("DUPLICATE_CONTAINER");
        return found.isEmpty() ? null : found.get(0);
    }

    static Element ensure(Document doc, Node parent, String name) throws Exception {
        Element e = one(parent, name);
        if (e == null) { e = doc.createElement(name); parent.appendChild(e); }
        return e;
    }

    static List<Element> triggerContainers(Document doc) throws Exception {
        Element root = doc.getDocumentElement();
        List<Element> result = new ArrayList<>();
        Element legacy = one(root, "triggers");
        if (legacy != null) result.add(legacy);
        Element property = one(one(root, "properties"), PROPERTY);
        Element canonical = one(property, "triggers");
        if (canonical != null) result.add(canonical);
        return result;
    }

    static List<Element> polls(Document doc) throws Exception {
        List<Element> found = new ArrayList<>();
        for (Element c : triggerContainers(doc)) found.addAll(named(c, SCM));
        if (found.size() > 1) throw new Exception("DUPLICATE_SCM_TRIGGERS");
        return found;
    }

    static void validate(Document doc) throws Exception {
        Element root = doc.getDocumentElement();
        if (!root.getTagName().equals("flow-definition")) throw new Exception("NOT_PIPELINE");
        Element definition = one(root, "definition");
        if (definition == null || !definition.getAttribute("class").equals(
                "org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition")) throw new Exception("NOT_SCM_PIPELINE");
        polls(doc);
    }

    // Include element/attribute names, text, CDATA, comments and processing instructions.
    // Ignore formatting whitespace only in parents which also have child elements.
    static void token(StringBuilder out, String value) { out.append(value.length()).append(':').append(value); }
    static boolean whitespace(String value) {
        return value.chars().allMatch(c -> c == 32 || c == 9 || c == 10 || c == 13);
    }
    static void describe(Node node, StringBuilder out) {
        token(out, String.valueOf(node.getNodeType()));
        token(out, node.getNodeName());
        token(out, node.getNodeValue() == null ? "" : node.getNodeValue());
        NamedNodeMap attrs = node.getAttributes();
        List<Node> sorted = new ArrayList<>();
        if (attrs != null) for (int i = 0; i < attrs.getLength(); i++) sorted.add(attrs.item(i));
        sorted.sort(Comparator.comparing(Node::getNodeName));
        out.append('[');
        for (Node attr : sorted) { token(out, attr.getNodeName()); token(out, attr.getNodeValue()); }
        out.append(']');
        boolean hasElements = !children(node).isEmpty();
        out.append('{');
        for (Node child = node.getFirstChild(); child != null; child = child.getNextSibling()) {
            if (hasElements && child.getNodeType() == Node.TEXT_NODE && whitespace(child.getNodeValue())) continue;
            describe(child, out);
        }
        out.append('}');
    }

    static String fingerprint(Node doc) throws Exception {
        StringBuilder description = new StringBuilder();
        describe(doc, description);
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(description.toString().getBytes(StandardCharsets.UTF_8)));
    }

    static boolean empty(Node node) {
        if (node == null || node.hasAttributes()) return false;
        for (Node n = node.getFirstChild(); n != null; n = n.getNextSibling())
            if (n.getNodeType() != Node.TEXT_NODE || !whitespace(n.getNodeValue())) return false;
        return true;
    }

    static String unrelatedFingerprint(Document input) throws Exception {
        Document doc = (Document)input.cloneNode(true);
        for (Element poll : polls(doc)) poll.getParentNode().removeChild(poll);
        for (Element container : triggerContainers(doc)) if (empty(container)) container.getParentNode().removeChild(container);
        Element root = doc.getDocumentElement();
        Element properties = one(root, "properties");
        Element property = one(properties, PROPERTY);
        // A property holding only the SCM trigger belongs to the permitted change.
        if (property != null && children(property).isEmpty() && whitespace(property.getTextContent()))
            properties.removeChild(property);
        if (empty(properties)) root.removeChild(properties);
        return fingerprint(doc);
    }

    static String serialize(Document doc) throws Exception {
        TransformerFactory factory = TransformerFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        Transformer transformer = factory.newTransformer();
        transformer.setOutputProperty(OutputKeys.VERSION, doc.getXmlVersion());
        transformer.setOutputProperty(OutputKeys.ENCODING, "UTF-8");
        transformer.setOutputProperty(OutputKeys.INDENT, "no");
        StringWriter out = new StringWriter();
        transformer.transform(new DOMSource(doc), new StreamResult(out));
        return out.toString();
    }

    static String patch(Document doc) throws Exception {
        String before = unrelatedFingerprint(doc);
        Element root = doc.getDocumentElement();
        Element container = ensure(doc, ensure(doc, ensure(doc, root, "properties"), PROPERTY), "triggers");
        List<Element> existing = polls(doc);
        Element poll = existing.isEmpty() ? doc.createElement(SCM) : existing.get(0);
        container.appendChild(poll);
        ensure(doc, poll, "spec").setTextContent(SCHEDULE);
        if (existing.isEmpty()) ensure(doc, poll, "ignorePostCommitHooks").setTextContent("false");
        if (!before.equals(unrelatedFingerprint(doc))) throw new Exception("UNRELATED_SETTINGS_CHANGED");
        String text = serialize(doc);
        Document reparsed = parse(text);
        validate(reparsed);
        if (!fingerprint(doc).equals(fingerprint(reparsed)) || !before.equals(unrelatedFingerprint(reparsed)))
            throw new Exception("ROUND_TRIP_CHANGED_SETTINGS");
        if (!doc.getXmlVersion().equals(reparsed.getXmlVersion())) throw new Exception("XML_VERSION_CHANGED");
        return text;
    }

    static void inspect(Document doc) throws Exception {
        List<Element> all = polls(doc);
        Element property = one(one(doc.getDocumentElement(), "properties"), PROPERTY);
        Element canonical = one(property, "triggers");
        String schedule = all.isEmpty() ? "" : one(all.get(0), "spec").getTextContent();
        // No raw settings/credential IDs in metadata. Encode schedule to avoid JSON escaping issues.
        String encoded = Base64.getEncoder().encodeToString(schedule.getBytes(StandardCharsets.UTF_8));
        int otherCount = 0;
        for (Element c : triggerContainers(doc)) for (Element e : children(c)) if (!e.getTagName().equals(SCM)) otherCount++;
        System.out.print("{\"version\":\"" + doc.getXmlVersion() + "\",\"pollCount\":" + all.size()
                + ",\"canonicalCount\":" + named(canonical, SCM).size() + ",\"scheduleBase64\":\"" + encoded
                + "\",\"otherCount\":" + otherCount + ",\"settingsHash\":\"" + unrelatedFingerprint(doc)
                + "\",\"pollHash\":\"" + (all.isEmpty() ? "" : fingerprint(all.get(0)))
                + "\",\"fullHash\":\"" + fingerprint(doc) + "\"}");
    }

    public static void main(String[] args) {
        try {
            String text = new String(System.in.readAllBytes(), StandardCharsets.UTF_8);
            Document doc = parse(text);
            validate(doc);
            if (args.length == 1 && args[0].equals("inspect")) inspect(doc);
            else if (args.length == 1 && args[0].equals("patch")) System.out.print(patch(doc));
            else throw new Exception("INVALID_MODE");
        } catch (Exception error) {
            // SAX/transformer messages may include raw configuration. Never print them.
            System.err.print("XML processing rejected: " + error.getClass().getSimpleName());
            System.exit(2);
        }
    }
}
