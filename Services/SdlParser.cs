using System;
using System.Collections.Generic;
using System.Linq;
using System.Xml;
using System.Xml.Linq;
using TradosKiller.Core.Models;
using System.Text.RegularExpressions;

namespace TradosKiller.Core.Services
{
    public class SdlParser
    {
        public List<TranslationSegment> ExtractSegments(string filePath)
        {
            try
            {
                var doc = XDocument.Load(filePath);
                
                return doc.Descendants().Where(d => d.Name.LocalName == "trans-unit").Select(unit => {
                    
                    var sourceElement = unit.Descendants().FirstOrDefault(d => d.Name.LocalName == "source");
                    var targetElement = unit.Descendants().FirstOrDefault(d => d.Name.LocalName == "target");

                    // Se não houver <target>, cria um vazio baseado no source
                    if (targetElement == null && sourceElement != null)
                    {
                        targetElement = new XElement(sourceElement.Name, "");
                        unit.Add(targetElement);
                    }

                    return new TranslationSegment
                    {
                        Id = unit.Attribute("id")?.Value ?? "",
                        // GetInnerXml limpa o lixo visual (<mrk>, xmlns) para o Grid
                        Source = sourceElement != null ? GetInnerXml(sourceElement) : "",
                        Target = targetElement != null ? GetInnerXml(targetElement) : ""
                    };
                }).ToList();
            }
            catch (Exception ex)
            {
                throw new Exception($"Erro ao ler o arquivo: {ex.Message}");
            }
        }

        public void SaveFile(string inputPath, string outputPath, List<TranslationSegment> segments)
        {
            try
            {
                var doc = XDocument.Load(inputPath);

                foreach (var seg in segments)
                {
                    // Busca a unidade pelo ID
                    var unit = doc.Descendants().Where(d => d.Name.LocalName == "trans-unit")
                                  .FirstOrDefault(u => !string.IsNullOrEmpty(seg.Id) && u.Attribute("id")?.Value == seg.Id);

                    if (unit != null)
                    {
                        var target = unit.Descendants().FirstOrDefault(d => d.Name.LocalName == "target");

                        if (target == null)
                        {
                            var source = unit.Descendants().FirstOrDefault(d => d.Name.LocalName == "source");
                            if (source != null)
                            {
                                target = new XElement(source.Name, "");
                                unit.Add(target);
                            }
                        }

                        if (target != null)
                        {
                            // Tenta gravar preservando tags se o usuário digitou XML válido
                            try
                            {
                                // Remove conteúdo antigo e injeta o novo
                                target.ReplaceNodes(XElement.Parse($"<root>{seg.Target}</root>").Nodes());
                            }
                            catch (XmlException)
                            {
                                // Se der erro de XML (tags mal fechadas), grava como texto puro para não crashar
                                target.Value = seg.Target ?? "";
                            }

                            // --- INJETOR DE STATUS (CONFIRMAÇÃO) ---
                            // Define o status no atributo principal
                            unit.SetAttributeValue("conf", "Translated");

                            // Busca a tag de metadata 'lp' (que pode ter prefixo sdl:lp)
                            var lp = unit.Descendants().FirstOrDefault(d => d.Name.LocalName == "lp");
                            if (lp != null)
                            {
                                lp.SetAttributeValue("status", "Translated");
                            }
                        }
                    }
                }

                // Limpeza final: remove declarações de namespace redundantes que o .NET enfia no meio do arquivo
                foreach (var el in doc.Descendants())
                {
                    el.Attributes().Where(a => a.IsNamespaceDeclaration && el.Parent != null).Remove();
                }

                doc.Save(outputPath);
            }
            catch (Exception ex)
            {
                throw new Exception($"Erro ao salvar o arquivo: {ex.Message}");
            }
        }

        private string GetInnerXml(XElement el)
        {
            if (el == null) return "";

            using (var reader = el.CreateReader())
            {
                reader.MoveToContent();
                string rawXml = reader.ReadInnerXml();
                return CleanXmlForDisplay(rawXml);
            }
        }

        private string CleanXmlForDisplay(string xml)
        {
            if (string.IsNullOrEmpty(xml)) return "";

            // 1. Remove as declarações de Namespace (xmlns)
            string result = Regex.Replace(xml, @"\s?xmlns[:\w]*=""[^""]+""", "");

            // 2. Remove tags <mrk> mas mantém o texto dentro
            result = Regex.Replace(result, @"<mrk\b[^>]*>", "");
            result = Regex.Replace(result, @"</mrk>", "");

            return result.Trim();
        }
    }
}