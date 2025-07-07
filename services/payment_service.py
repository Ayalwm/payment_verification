# services/payment_service.py
from abc import ABC, abstractmethod
from models import TransactionDetails, VerificationResult, PaymentProviderName

class PaymentService(ABC):
    """
    Abstract base class for all payment verification services.
    Defines the common interface that all concrete payment services must implement.
    """

    @property
    @abstractmethod
    def provider_name(self) -> PaymentProviderName:
        """Returns the name of the payment provider this service handles."""
        pass

    @abstractmethod
    async def verify_payment(self, transaction_details: TransactionDetails) -> VerificationResult:
        """
        Abstract method to verify a payment transaction.

        Args:
            transaction_details (TransactionDetails): The details of the transaction to verify.

        Returns:
            VerificationResult: The result of the verification, including status and data.
        """
        pass