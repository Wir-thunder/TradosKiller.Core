namespace TradosKiller.Core.Models
{
    public class TranslationSegment
    {
        public string Id { get; set; } = string.Empty;
        public string Source { get; set; } = string.Empty;
        public string Target { get; set; } = string.Empty;
        public bool IsConfirmed { get; set; } = false;
    }
}