"""Bedrock Knowledge Base on S3 Vectors — never OpenSearch (ADR-007)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct

from supportrouter_infra.constants import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_ID,
    PROJECT_NAME,
)


class KnowledgeBaseStack(cdk.Stack):
    """Explicit S3 Vectors wiring. No AOSS. No standing ingestion schedule."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        docs_bucket = s3.Bucket(
            self,
            "KbDocsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=False,
        )

        vector_bucket_name = cdk.Fn.sub(
            f"{PROJECT_NAME}-vectors-${{AWS::AccountId}}"
        )
        index_name = f"{PROJECT_NAME}-kb-index"

        vector_bucket = s3vectors.CfnVectorBucket(
            self,
            "VectorBucket",
            vector_bucket_name=vector_bucket_name,
        )
        vector_bucket.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        vector_index = s3vectors.CfnIndex(
            self,
            "VectorIndex",
            vector_bucket_name=vector_bucket_name,
            index_name=index_name,
            data_type="float32",
            dimension=EMBEDDING_DIMENSIONS,
            distance_metric="cosine",
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=[
                    "AMAZON_BEDROCK_TEXT",
                    "AMAZON_BEDROCK_METADATA",
                ],
            ),
        )
        vector_index.add_dependency(vector_bucket)
        vector_index.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        kb_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="SupportRouter Bedrock KB role (S3 Vectors only)",
        )
        docs_bucket.grant_read(kb_role)
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3vectors:QueryVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:PutVectors",
                    "s3vectors:DeleteVectors",
                    "s3vectors:GetIndex",
                    "s3vectors:ListIndexes",
                    "s3vectors:GetVectorBucket",
                ],
                resources=["*"],
            )
        )
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/{EMBEDDING_MODEL_ID}",
                ],
            )
        )

        knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=f"{PROJECT_NAME}-kb",
            description="VoltEdge synthetic FAQ/policy KB on S3 Vectors (ADR-007)",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=(
                        f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/{EMBEDDING_MODEL_ID}"
                    ),
                    embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                        bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                            dimensions=EMBEDDING_DIMENSIONS,
                        ),
                    ),
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=vector_index.attr_index_arn,
                ),
            ),
        )
        knowledge_base.node.add_dependency(kb_role)
        knowledge_base.add_dependency(vector_index)

        data_source = bedrock.CfnDataSource(
            self,
            "KbDataSource",
            name=f"{PROJECT_NAME}-kb-docs",
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=docs_bucket.bucket_arn,
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=512,
                        overlap_percentage=20,
                    ),
                ),
            ),
        )

        # Intentionally NO S3 event → StartIngestionJob automation (ADR-008: on-demand reseed only).

        self.docs_bucket = docs_bucket
        self.knowledge_base_id = knowledge_base.attr_knowledge_base_id
        self.data_source_id = data_source.attr_data_source_id

        cdk.CfnOutput(self, "KbDocsBucketName", value=docs_bucket.bucket_name)
        cdk.CfnOutput(self, "KnowledgeBaseId", value=knowledge_base.attr_knowledge_base_id)
        cdk.CfnOutput(self, "DataSourceId", value=data_source.attr_data_source_id)
        cdk.CfnOutput(self, "VectorStoreType", value="S3_VECTORS")
        cdk.CfnOutput(
            self,
            "OpenSearchForbidden",
            value="true",
            description="ADR-007: OpenSearch Serverless must never be used",
        )

        cdk.Tags.of(self).add("Project", PROJECT_NAME)
        cdk.Tags.of(self).add("VectorStore", "S3_VECTORS")
